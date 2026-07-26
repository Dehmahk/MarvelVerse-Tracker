"""Milestone 10: personal data export/import.

Unlike backups (see ``services.backup_service``, a full copy of the
whole SQLite file), this module exports only the user's own activity --
watched/favorite/wishlist/rating/notes/rewatch counts, the full watch
history log, and achievement progress -- as a portable JSON file, keyed
by each project's ``slug`` rather than its local database id. That's the
one part of this app's data that can never be reconstructed by a TMDB
re-sync (see every model docstring in ``models/user_data.py`` and
``models/watch_history.py`` for why that separation exists in the first
place); the canonical catalog itself is trivially rebuilt any time via
Settings' "Sync from TMDB" button, so exporting it too would only bloat
the file without protecting anything irreplaceable.

This makes the export meaningful across installs (a fresh install synced
against the same TMDB catalog will assign different local ids, but the
same slugs) and machines, at the cost of an import being unable to
restore personal data for a project that hasn't been synced/created
locally yet -- callers must sync from TMDB (or otherwise create the
matching projects) before importing data for them.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from database import session_scope
from models import Achievement, Project, UserAchievement, UserProjectData, WatchHistoryEntry

logger = logging.getLogger(__name__)

# Bumped only if the export schema below ever changes shape in a way that
# would break parsing an older file -- import_user_data() refuses to read
# anything with an unrecognized version rather than guessing.
EXPORT_FORMAT_VERSION = 1


@dataclass(frozen=True)
class ExportSummary:
    export_path: Path
    project_count: int
    watch_history_count: int
    achievement_count: int


@dataclass(frozen=True)
class ImportSummary:
    matched_count: int
    skipped_slugs: tuple[str, ...]
    watch_history_imported: int
    achievements_restored: int

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_slugs)

    def summary(self) -> str:
        parts = [f"{self.matched_count} project(s) restored"]
        if self.watch_history_imported:
            parts.append(f"{self.watch_history_imported} watch log entries")
        if self.achievements_restored:
            parts.append(f"{self.achievements_restored} achievements")
        if self.skipped_count:
            parts.append(f"{self.skipped_count} skipped (not synced locally)")
        return ", ".join(parts)


def _iso_or_none(value) -> str | None:
    return value.isoformat() if value is not None else None


def export_user_data(export_path: Path) -> ExportSummary:
    """Write every project's personal data, the full watch history log,
    and achievement progress to ``export_path`` as JSON. Owns its own
    session scope, like every other service function in this codebase."""
    with session_scope() as session:
        user_data_rows = session.scalars(
            select(UserProjectData).options(joinedload(UserProjectData.project))
        ).all()

        projects_payload: dict[str, dict] = {}
        for row in user_data_rows:
            # Skip rows that are just the default, all-untouched state --
            # every project gets one created lazily on first edit (see
            # services.project_service._get_or_create_user_data), so most
            # libraries have plenty of these that carry no real signal.
            if not (row.watched or row.favorite or row.wishlist or row.rating is not None or row.notes or row.rewatch_count):
                continue
            projects_payload[row.project.slug] = {
                "watched": row.watched,
                "favorite": row.favorite,
                "wishlist": row.wishlist,
                "rating": row.rating,
                "notes": row.notes,
                "rewatch_count": row.rewatch_count,
                "last_watched_date": _iso_or_none(row.last_watched_date),
            }

        history_rows = session.scalars(
            select(WatchHistoryEntry).options(joinedload(WatchHistoryEntry.project))
        ).all()
        history_payload = [
            {
                "slug": entry.project.slug,
                "watched_at": entry.watched_at.isoformat(),
                "is_rewatch": entry.is_rewatch,
                "notes": entry.notes,
            }
            for entry in history_rows
        ]

        achievement_rows = session.scalars(
            select(UserAchievement).options(joinedload(UserAchievement.achievement))
        ).all()
        achievements_payload = {
            row.achievement.key: {
                "progress_current": row.progress_current,
                "unlocked_at": _iso_or_none(row.unlocked_at),
            }
            for row in achievement_rows
            if row.progress_current or row.unlocked_at is not None
        }

    payload = {
        "format_version": EXPORT_FORMAT_VERSION,
        "exported_at": datetime.now().isoformat(),
        "projects": projects_payload,
        "watch_history": history_payload,
        "achievements": achievements_payload,
    }

    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info(
        "Exported user data to %s: %d projects, %d watch history entries, %d achievements",
        export_path,
        len(projects_payload),
        len(history_payload),
        len(achievements_payload),
    )
    return ExportSummary(
        export_path=export_path,
        project_count=len(projects_payload),
        watch_history_count=len(history_payload),
        achievement_count=len(achievements_payload),
    )


def _parse_date(raw: str | None) -> date | None:
    return date.fromisoformat(raw) if raw else None


def _parse_datetime(raw: str | None) -> datetime | None:
    return datetime.fromisoformat(raw) if raw else None


def import_user_data(import_path: Path) -> ImportSummary:
    """Read a file written by :func:`export_user_data` and merge it into
    the current database, matching projects by ``slug``.

    Every matched project's personal-data fields are overwritten
    outright (this is an explicit, user-initiated restore/migrate
    action, not a passive background sync -- unlike a TMDB sync, which
    never touches this data at all). A project with no local match
    (never synced, or synced under a different slug) is skipped and
    reported rather than raising -- restoring most of a library
    shouldn't be all-or-nothing over one missing title. Watch history
    entries are only inserted if an equivalent one (same project,
    timestamp, and rewatch flag) doesn't already exist, so re-importing
    the same file twice is safe. Achievement progress is merged
    non-destructively: progress only ever moves up
    (``max(current, imported)``), and an unlock timestamp already
    recorded locally is never overwritten by an imported one.

    Raises ``ValueError`` if the file isn't valid JSON, isn't shaped
    like an export, or has a ``format_version`` this version of the app
    doesn't recognize.
    """
    try:
        payload = json.loads(import_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"'{import_path.name}' is not a valid JSON file.") from exc

    if not isinstance(payload, dict) or "projects" not in payload:
        raise ValueError(f"'{import_path.name}' doesn't look like a MarvelVerse Tracker export.")

    format_version = payload.get("format_version")
    if format_version != EXPORT_FORMAT_VERSION:
        raise ValueError(
            f"'{import_path.name}' has an unrecognized export format "
            f"(version {format_version!r}) -- this version of the app only understands "
            f"version {EXPORT_FORMAT_VERSION}."
        )

    matched_slugs: list[str] = []
    skipped_slugs: list[str] = []
    watch_history_imported = 0
    achievements_restored = 0

    with session_scope() as session:
        for slug, fields in payload.get("projects", {}).items():
            project = session.scalar(select(Project).where(Project.slug == slug))
            if project is None:
                skipped_slugs.append(slug)
                continue

            user_data = session.scalar(select(UserProjectData).where(UserProjectData.project_id == project.id))
            if user_data is None:
                user_data = UserProjectData(project_id=project.id)
                session.add(user_data)

            user_data.watched = bool(fields.get("watched", False))
            user_data.favorite = bool(fields.get("favorite", False))
            user_data.wishlist = bool(fields.get("wishlist", False))
            user_data.rating = fields.get("rating")
            user_data.notes = fields.get("notes")
            user_data.rewatch_count = int(fields.get("rewatch_count", 0))
            user_data.last_watched_date = _parse_date(fields.get("last_watched_date"))
            matched_slugs.append(slug)

        session.flush()
        project_id_by_slug = {
            slug: session.scalar(select(Project.id).where(Project.slug == slug)) for slug in matched_slugs
        }

        # Deliberately built and checked in Python rather than as a SQL
        # WHERE clause: SQLite stores DateTime columns as TEXT, and a
        # client-supplied datetime (this import) round-trips through a
        # different string format than one written by the database's own
        # server_default=func.now() (e.g. log_watch()'s original entry) --
        # a SQL-level equality comparison between the two can silently
        # miss an otherwise-identical timestamp. Loading existing rows
        # back as real Python datetime objects and comparing those
        # sidesteps the formatting mismatch entirely.
        existing_history_keys = set(
            session.execute(
                select(
                    WatchHistoryEntry.project_id,
                    WatchHistoryEntry.watched_at,
                    WatchHistoryEntry.is_rewatch,
                )
            ).all()
        )

        for entry in payload.get("watch_history", []):
            slug = entry.get("slug")
            project_id = project_id_by_slug.get(slug)
            if project_id is None:
                continue  # already reported once via skipped_slugs above

            watched_at = _parse_datetime(entry.get("watched_at"))
            is_rewatch = bool(entry.get("is_rewatch", False))
            key = (project_id, watched_at, is_rewatch)
            if key in existing_history_keys:
                continue
            existing_history_keys.add(key)  # guards against a duplicated entry within the same file too

            session.add(
                WatchHistoryEntry(
                    project_id=project_id,
                    watched_at=watched_at,
                    is_rewatch=is_rewatch,
                    notes=entry.get("notes"),
                )
            )
            watch_history_imported += 1

        for key, progress in payload.get("achievements", {}).items():
            achievement = session.scalar(select(Achievement).where(Achievement.key == key))
            if achievement is None:
                continue  # an export from a newer app version defining achievements this one doesn't know

            user_achievement = session.scalar(
                select(UserAchievement).where(UserAchievement.achievement_id == achievement.id)
            )
            if user_achievement is None:
                user_achievement = UserAchievement(achievement_id=achievement.id)
                session.add(user_achievement)

            imported_progress = int(progress.get("progress_current", 0))
            user_achievement.progress_current = max(user_achievement.progress_current, imported_progress)
            if user_achievement.unlocked_at is None:
                imported_unlocked_at = _parse_datetime(progress.get("unlocked_at"))
                if imported_unlocked_at is not None:
                    user_achievement.unlocked_at = imported_unlocked_at
                    achievements_restored += 1

    logger.info(
        "Imported user data from %s: %d matched, %d skipped, %d watch history entries, %d achievements",
        import_path,
        len(matched_slugs),
        len(skipped_slugs),
        watch_history_imported,
        achievements_restored,
    )
    return ImportSummary(
        matched_count=len(matched_slugs),
        skipped_slugs=tuple(skipped_slugs),
        watch_history_imported=watch_history_imported,
        achievements_restored=achievements_restored,
    )
