from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from settings.defaults import (
    DEFAULT_ACCENT,
    DEFAULT_ACHIEVEMENT_SOUND_ENABLED,
    DEFAULT_ANIMATIONS_ENABLED,
    DEFAULT_APPLICATION_NAME,
    DEFAULT_AUTO_BACKUP_ENABLED,
    DEFAULT_AUTO_BACKUP_INTERVAL_DAYS,
    DEFAULT_AUTO_BACKUP_RETENTION_COUNT,
    DEFAULT_CACHE_SIZE_LIMIT_MB,
    DEFAULT_CONFIRM_BEFORE_DELETE,
    DEFAULT_DATE_FORMAT,
    DEFAULT_ENABLE_TRAILER_EMBED,
    DEFAULT_FONT_SCALE,
    DEFAULT_LANDING_PAGE,
    DEFAULT_LIBRARY_PAGE_SIZE,
    DEFAULT_LIBRARY_SHOW_UPCOMING,
    DEFAULT_LIBRARY_SORT_DIRECTION,
    DEFAULT_LIBRARY_SORT_FIELD,
    DEFAULT_LIBRARY_VIEW_MODE,
    DEFAULT_MASK_RATINGS,
    DEFAULT_NOTIFY_ACHIEVEMENT_UNLOCKS,
    DEFAULT_NOTIFY_STATUS_MESSAGES,
    DEFAULT_POSTER_CARD_SIZE,
    DEFAULT_RATING_SCALE,
    DEFAULT_THEME,
    DEFAULT_TIMELINE_EXCLUDED_SAGAS,
    DEFAULT_TIMELINE_SORT_MODE,
    DEFAULT_TMDB_AUTO_SYNC_INTERVAL_DAYS,
)

# Reading the key from the environment lets a developer/CI box run a sync
# without ever writing a secret to config.json. The env var always wins over
# whatever is saved on disk -- see resolved_tmdb_api_key().
TMDB_API_KEY_ENV_VAR = "TMDB_API_KEY"


def _default_data_root() -> Path:
    """Where the database, poster cache, logs, and config.json live by
    default, before any explicit override.

    Running from source (``python main.py``), this stays the project's
    own "data"/"cache"/"logs" folders (i.e. just "."), which is
    convenient for development -- everything lives right next to the
    code, easy to find and easy to wipe.

    Packaged as an executable, the current working directory isn't a
    reliable writable location -- it could be Program Files (which
    typically requires elevation to write to), a read-only mount, or
    just whatever directory the OS happened to launch from -- so this
    resolves to a proper per-user application-data directory instead:
    ``%LOCALAPPDATA%`` on Windows, ``~/Library/Application Support`` on
    macOS, ``$XDG_DATA_HOME`` (or ``~/.local/share``) on Linux.
    """
    if not getattr(sys, "frozen", False):
        return Path(".")

    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))

    return base / "MarvelVerseTracker"


@dataclass
class AppConfig:
    application_name: str = DEFAULT_APPLICATION_NAME
    theme: str = DEFAULT_THEME
    accent_color: str = DEFAULT_ACCENT
    data_directory: Path = field(default_factory=lambda: _default_data_root() / "data")
    cache_directory: Path = field(default_factory=lambda: _default_data_root() / "cache")
    log_directory: Path = field(default_factory=lambda: _default_data_root() / "logs")

    # --- Milestone 8: TMDB API integration ----------------------------------
    # The user-entered key, persisted to config.json via the Settings page.
    # Never read this field directly to make a request -- always go through
    # resolved_tmdb_api_key(), which lets TMDB_API_KEY_ENV_VAR override it.
    tmdb_api_key: str | None = None
    # Set to True the first time an automatic startup sync is attempted
    # (regardless of whether it succeeded), so the app only ever tries the
    # "sync automatically on first run" behavior once and never nags again
    # on subsequent launches.
    tmdb_auto_sync_attempted: bool = False
    # 0 disables scheduled re-syncing entirely (the one-shot first-launch
    # sync above is all that ever runs). > 0 means "re-sync automatically
    # if it's been at least this many days since the last successful sync".
    tmdb_auto_sync_interval_days: int = DEFAULT_TMDB_AUTO_SYNC_INTERVAL_DAYS
    # Naive-UTC ISO timestamp string (or None) of the last sync that
    # actually completed, scheduled or manual -- the anchor
    # tmdb_auto_sync_interval_days counts forward from.
    tmdb_last_synced_at: str | None = None

    # --- Milestone 11/12: Library & Browsing defaults -----------------------
    library_default_view_mode: str = DEFAULT_LIBRARY_VIEW_MODE
    library_default_sort_field: str = DEFAULT_LIBRARY_SORT_FIELD
    library_default_sort_direction: str = DEFAULT_LIBRARY_SORT_DIRECTION
    library_default_page_size: int = DEFAULT_LIBRARY_PAGE_SIZE
    library_show_upcoming: bool = DEFAULT_LIBRARY_SHOW_UPCOMING

    # --- Timeline ------------------------------------------------------------
    timeline_default_sort_mode: str = DEFAULT_TIMELINE_SORT_MODE
    timeline_excluded_sagas: list[str] = field(
        default_factory=lambda: list(DEFAULT_TIMELINE_EXCLUDED_SAGAS)
    )

    # --- Appearance ------------------------------------------------------------
    font_scale: float = DEFAULT_FONT_SCALE
    poster_card_size: int = DEFAULT_POSTER_CARD_SIZE
    animations_enabled: bool = DEFAULT_ANIMATIONS_ENABLED
    enable_trailer_embed: bool = DEFAULT_ENABLE_TRAILER_EMBED

    # --- Data & Sync -----------------------------------------------------------
    cache_size_limit_mb: int = DEFAULT_CACHE_SIZE_LIMIT_MB
    auto_backup_enabled: bool = DEFAULT_AUTO_BACKUP_ENABLED
    auto_backup_interval_days: int = DEFAULT_AUTO_BACKUP_INTERVAL_DAYS
    auto_backup_retention_count: int = DEFAULT_AUTO_BACKUP_RETENTION_COUNT
    # Naive-UTC ISO timestamp string (or None) of the last backup the
    # scheduler itself created (manual "Create Backup" clicks don't count),
    # the anchor auto_backup_interval_days counts forward from.
    auto_backup_last_run_at: str | None = None

    # --- Notifications -----------------------------------------------------------
    notify_achievement_unlocks: bool = DEFAULT_NOTIFY_ACHIEVEMENT_UNLOCKS
    notify_status_messages: bool = DEFAULT_NOTIFY_STATUS_MESSAGES
    achievement_sound_enabled: bool = DEFAULT_ACHIEVEMENT_SOUND_ENABLED

    # --- Personalization -----------------------------------------------------------
    rating_scale: str = DEFAULT_RATING_SCALE
    date_format: str = DEFAULT_DATE_FORMAT
    default_landing_page: str = DEFAULT_LANDING_PAGE

    # --- Privacy -----------------------------------------------------------------
    confirm_before_delete: bool = DEFAULT_CONFIRM_BEFORE_DELETE
    mask_ratings: bool = DEFAULT_MASK_RATINGS

    # --- Window state --------------------------------------------------------------
    # Hex-encoded QMainWindow.saveGeometry() output (size, position, and
    # maximized/fullscreen state all in one blob) -- Qt's own recommended
    # pattern for this, rather than tracking width/height/x/y/maximized as
    # separate fields ourselves. None on a fresh install, in which case
    # MainWindow falls back to its hardcoded 1440x900 default size.
    window_geometry: str | None = None

    @property
    def database_file(self) -> Path:
        return self.data_directory / "marvelverse.db"

    @property
    def log_file(self) -> Path:
        return self.log_directory / "application.log"

    @property
    def config_file(self) -> Path:
        return self.data_directory / "config.json"

    def resolved_tmdb_api_key(self) -> str | None:
        """The API key to actually use for a TMDB request.

        ``TMDB_API_KEY_ENV_VAR`` always wins over the persisted
        ``tmdb_api_key`` field so a developer/CI box can run a sync without
        ever writing a secret to ``config.json``. Returns ``None`` (rather
        than an empty string) if neither is set/non-blank.
        """
        env_value = os.environ.get(TMDB_API_KEY_ENV_VAR, "").strip()
        if env_value:
            return env_value
        return self.tmdb_api_key.strip() if self.tmdb_api_key and self.tmdb_api_key.strip() else None

    def ensure_directories(self) -> None:
        self.data_directory.mkdir(parents=True, exist_ok=True)
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        self.log_directory.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        self.ensure_directories()
        payload = asdict(self)
        payload["data_directory"] = str(self.data_directory)
        payload["cache_directory"] = str(self.cache_directory)
        payload["log_directory"] = str(self.log_directory)

        self.config_file.write_text(
            json.dumps(payload, indent=4),
            encoding="utf-8",
        )

    @classmethod
    def load(cls) -> "AppConfig":
        config = cls()

        if config.config_file.exists():
            try:
                data = json.loads(config.config_file.read_text(encoding="utf-8"))
                defaults = cls()
                config = cls(
                    application_name=data.get("application_name", DEFAULT_APPLICATION_NAME),
                    theme=data.get("theme", DEFAULT_THEME),
                    accent_color=data.get("accent_color", DEFAULT_ACCENT),
                    data_directory=Path(data.get("data_directory", str(defaults.data_directory))),
                    cache_directory=Path(data.get("cache_directory", str(defaults.cache_directory))),
                    log_directory=Path(data.get("log_directory", str(defaults.log_directory))),
                    tmdb_api_key=data.get("tmdb_api_key"),
                    tmdb_auto_sync_attempted=bool(data.get("tmdb_auto_sync_attempted", False)),
                    tmdb_auto_sync_interval_days=int(
                        data.get(
                            "tmdb_auto_sync_interval_days", defaults.tmdb_auto_sync_interval_days
                        )
                    ),
                    tmdb_last_synced_at=data.get("tmdb_last_synced_at"),
                    library_default_view_mode=data.get(
                        "library_default_view_mode", defaults.library_default_view_mode
                    ),
                    library_default_sort_field=data.get(
                        "library_default_sort_field", defaults.library_default_sort_field
                    ),
                    library_default_sort_direction=data.get(
                        "library_default_sort_direction", defaults.library_default_sort_direction
                    ),
                    library_default_page_size=int(
                        data.get("library_default_page_size", defaults.library_default_page_size)
                    ),
                    library_show_upcoming=bool(
                        data.get("library_show_upcoming", defaults.library_show_upcoming)
                    ),
                    timeline_default_sort_mode=data.get(
                        "timeline_default_sort_mode", defaults.timeline_default_sort_mode
                    ),
                    timeline_excluded_sagas=list(
                        data.get("timeline_excluded_sagas", defaults.timeline_excluded_sagas)
                    ),
                    font_scale=float(data.get("font_scale", defaults.font_scale)),
                    poster_card_size=int(data.get("poster_card_size", defaults.poster_card_size)),
                    animations_enabled=bool(
                        data.get("animations_enabled", defaults.animations_enabled)
                    ),
                    enable_trailer_embed=bool(
                        data.get("enable_trailer_embed", defaults.enable_trailer_embed)
                    ),
                    cache_size_limit_mb=int(
                        data.get("cache_size_limit_mb", defaults.cache_size_limit_mb)
                    ),
                    auto_backup_enabled=bool(
                        data.get("auto_backup_enabled", defaults.auto_backup_enabled)
                    ),
                    auto_backup_interval_days=int(
                        data.get("auto_backup_interval_days", defaults.auto_backup_interval_days)
                    ),
                    auto_backup_retention_count=int(
                        data.get(
                            "auto_backup_retention_count", defaults.auto_backup_retention_count
                        )
                    ),
                    auto_backup_last_run_at=data.get("auto_backup_last_run_at"),
                    notify_achievement_unlocks=bool(
                        data.get("notify_achievement_unlocks", defaults.notify_achievement_unlocks)
                    ),
                    notify_status_messages=bool(
                        data.get("notify_status_messages", defaults.notify_status_messages)
                    ),
                    achievement_sound_enabled=bool(
                        data.get("achievement_sound_enabled", defaults.achievement_sound_enabled)
                    ),
                    rating_scale=data.get("rating_scale", defaults.rating_scale),
                    date_format=data.get("date_format", defaults.date_format),
                    default_landing_page=data.get(
                        "default_landing_page", defaults.default_landing_page
                    ),
                    confirm_before_delete=bool(
                        data.get("confirm_before_delete", defaults.confirm_before_delete)
                    ),
                    mask_ratings=bool(data.get("mask_ratings", defaults.mask_ratings)),
                    window_geometry=data.get("window_geometry"),
                )
            except (OSError, ValueError, TypeError):
                config = cls()

        config.ensure_directories()
        return config
