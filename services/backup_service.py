"""Milestone 10: database backups.

The whole app lives in a single SQLite file
(``AppConfig.database_file``), so a "backup" is just a timestamped copy
of that file -- no separate backup format needed. The only wrinkle is
that this database runs in WAL mode (see ``database/connection.py``),
which means recent writes can still be sitting in a ``-wal`` sidecar
file rather than the main database file, so a backup taken with a naive
file copy could silently miss them. ``create_backup()`` checkpoints WAL
back into the main file first to guarantee every backup is a complete,
self-contained snapshot with no sidecar files of its own.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from database import dispose_engine, init_database, session_scope
from settings.config import AppConfig

logger = logging.getLogger(__name__)

BACKUP_DIR_NAME = "backups"
BACKUP_FILENAME_PREFIX = "marvelverse-backup-"
BACKUP_FILENAME_SUFFIX = ".db"
_BACKUP_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"


@dataclass(frozen=True)
class BackupInfo:
    """A flat, detached-safe read model for one backup file on disk."""

    path: Path
    created_at: datetime
    size_bytes: int

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def size_display(self) -> str:
        size = self.size_bytes
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


def backups_directory(config: AppConfig) -> Path:
    return config.data_directory / BACKUP_DIR_NAME


def _checkpoint_wal() -> None:
    """Flushes any writes still sitting in the WAL file back into the
    main database file, so a plain file copy of the main file alone is
    guaranteed to be complete and self-contained."""
    with session_scope() as session:
        session.execute(text("PRAGMA wal_checkpoint(FULL)"))


def create_backup(config: AppConfig) -> BackupInfo:
    """Checkpoint WAL and copy the live database file to a new,
    timestamped file in ``backups_directory(config)``. Safe to call while
    the app is running normally -- it never disposes or reconnects the
    engine, unlike :func:`restore_backup`."""
    _checkpoint_wal()

    backup_dir = backups_directory(config)
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime(_BACKUP_TIMESTAMP_FORMAT)
    backup_path = backup_dir / f"{BACKUP_FILENAME_PREFIX}{timestamp}{BACKUP_FILENAME_SUFFIX}"
    # Vanishingly unlikely (same-second repeat calls), but guard against
    # silently overwriting an existing backup rather than ever doing so.
    suffix = 2
    while backup_path.exists():
        backup_path = backup_dir / f"{BACKUP_FILENAME_PREFIX}{timestamp}-{suffix}{BACKUP_FILENAME_SUFFIX}"
        suffix += 1

    shutil.copy2(config.database_file, backup_path)
    logger.info("Created database backup at %s", backup_path)

    stat = backup_path.stat()
    return BackupInfo(path=backup_path, created_at=datetime.fromtimestamp(stat.st_mtime), size_bytes=stat.st_size)


def list_backups(config: AppConfig) -> tuple[BackupInfo, ...]:
    """List every backup file, newest first. Reads mtime/size straight
    off disk rather than trying to parse the timestamp back out of the
    filename, so a manually-renamed or manually-copied-in backup file
    still shows up correctly."""
    backup_dir = backups_directory(config)
    if not backup_dir.exists():
        return ()

    infos = []
    for path in backup_dir.glob(f"{BACKUP_FILENAME_PREFIX}*{BACKUP_FILENAME_SUFFIX}"):
        stat = path.stat()
        infos.append(
            BackupInfo(path=path, created_at=datetime.fromtimestamp(stat.st_mtime), size_bytes=stat.st_size)
        )
    infos.sort(key=lambda info: info.created_at, reverse=True)
    return tuple(infos)


def delete_backup(backup_path: Path) -> None:
    """Removes one backup file. Raises FileNotFoundError if it's already
    gone, same as the underlying ``Path.unlink()`` -- callers decide how
    to surface that (e.g. treat it as already-done rather than an error)."""
    backup_path.unlink()
    logger.info("Deleted backup %s", backup_path)


def restore_backup(config: AppConfig, backup_path: Path) -> None:
    """Replace the live database with the contents of ``backup_path``.

    Unlike every other function in this module, this one *does* touch
    the database engine lifecycle directly: it disposes the current
    engine (closing every open connection so the file can be safely
    overwritten on every platform, including Windows, where an
    open/locked file can't be replaced), copies the backup over the live
    database file, removes any leftover ``-wal``/``-shm`` sidecar files
    from the *old* database so a stale one can never shadow the restored
    data, and finally re-initializes the engine and re-runs migrations
    via the same :func:`database.init_database` the app calls on normal
    startup -- so the running app can keep going immediately afterward
    without requiring a restart.
    """
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    dispose_engine()

    database_file = config.database_file
    shutil.copy2(backup_path, database_file)

    for sidecar_suffix in ("-wal", "-shm"):
        sidecar = database_file.with_name(database_file.name + sidecar_suffix)
        sidecar.unlink(missing_ok=True)

    # seed=True is safe (and a no-op) even against a database that
    # already has reference data -- seeding only ever inserts rows that
    # don't already exist, per database.seed.reference_data's own
    # idempotency guarantee.
    init_database(database_file, seed=True)
    logger.info("Restored database from backup %s", backup_path)


def maybe_run_scheduled_backup(config: AppConfig) -> BackupInfo | None:
    """Create an automatic backup if the Settings > Data & Sync "Automatic
    backups" toggle is on and enough time has passed since the last one.

    Called once at startup, same shape as the existing one-shot TMDB
    auto-sync check -- cheap to call every launch since it's a no-op
    unless a real backup is actually due. Returns the new
    :class:`BackupInfo` if one was created, else ``None`` (feature
    disabled, or not due yet).

    After creating a backup, prunes the oldest ones beyond
    ``config.auto_backup_retention_count`` -- manually-created backups
    count toward this limit too (there's no reliable way to tell them
    apart from a scheduled one after the fact, and a user who's manually
    backing up a lot presumably still wants *some* cap), so a retention
    count of 5 means "keep at most 5 backups total", not "5 scheduled
    ones on top of whatever else exists."

    Mutates and does *not* save ``config`` itself -- same pattern as
    ``tmdb_auto_sync_attempted`` elsewhere: the caller (ApplicationController)
    owns when config.save() actually happens.
    """
    if not config.auto_backup_enabled:
        return None

    if config.auto_backup_last_run_at is not None:
        try:
            last_run = datetime.fromisoformat(config.auto_backup_last_run_at)
        except ValueError:
            last_run = None
    else:
        last_run = None

    if last_run is not None:
        days_since = (datetime.now() - last_run).total_seconds() / 86400
        if days_since < config.auto_backup_interval_days:
            return None

    backup = create_backup(config)
    config.auto_backup_last_run_at = datetime.now().isoformat()

    retention = max(1, config.auto_backup_retention_count)
    existing = list_backups(config)
    for stale in existing[retention:]:
        try:
            delete_backup(stale.path)
        except FileNotFoundError:
            pass

    return backup
