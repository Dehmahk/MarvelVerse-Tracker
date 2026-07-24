DEFAULT_APPLICATION_NAME = "MarvelVerse Tracker"
DEFAULT_THEME = "dark"
DEFAULT_ACCENT = "#E62429"

# --- Library & Browsing ------------------------------------------------------
DEFAULT_LIBRARY_VIEW_MODE = "grid"  # one of views.pages.library_view.VIEW_MODES
DEFAULT_LIBRARY_SORT_FIELD = "title"  # services.project_service.SortField value
DEFAULT_LIBRARY_SORT_DIRECTION = "asc"  # services.project_service.SortDirection value
DEFAULT_LIBRARY_PAGE_SIZE = 24  # matches services.project_service.DEFAULT_PAGE_SIZE
DEFAULT_LIBRARY_SHOW_UPCOMING = True

# --- Timeline -----------------------------------------------------------------
DEFAULT_TIMELINE_SORT_MODE = "phase"  # services.timeline_service.TimelineSortMode value
# Matches services.timeline_service.SAGAS_EXCLUDED_FROM_CHRONOLOGICAL's
# original hardcoded set -- now the *default* rather than the only option,
# since Settings lets the user edit this list per-catalog.
DEFAULT_TIMELINE_EXCLUDED_SAGAS = (
    "Documentaries & Making-Of",
    "Marvel Studios Specials & Extras",
    "Junior & Spin-off Shows",
)

# --- Appearance -----------------------------------------------------------------
DEFAULT_FONT_SCALE = 1.0
DEFAULT_POSTER_CARD_SIZE = 160  # px, Library grid/poster card width
DEFAULT_ANIMATIONS_ENABLED = True

# Off by default: QtWebEngine (needed to embed a trailer player directly
# in Project Details) is a genuinely heavy dependency, and testing it
# surfaced a real risk -- on at least some machines/environments, a
# failure isn't a catchable Python exception at all, it's a hard
# process-level abort from Chromium's own sandboxing refusing to run.
# No amount of try/except in this app's own code can protect against
# that. The "Watch Trailer" button (opens the real browser) is always
# available regardless of this setting.
DEFAULT_ENABLE_TRAILER_EMBED = True

# --- Data & Sync ----------------------------------------------------------------
DEFAULT_TMDB_AUTO_SYNC_INTERVAL_DAYS = 0  # 0 = only the one-time first-launch sync
DEFAULT_CACHE_SIZE_LIMIT_MB = 500
DEFAULT_AUTO_BACKUP_ENABLED = False
DEFAULT_AUTO_BACKUP_INTERVAL_DAYS = 7
DEFAULT_AUTO_BACKUP_RETENTION_COUNT = 5

# --- Notifications --------------------------------------------------------------
DEFAULT_NOTIFY_ACHIEVEMENT_UNLOCKS = True
DEFAULT_NOTIFY_STATUS_MESSAGES = True
DEFAULT_ACHIEVEMENT_SOUND_ENABLED = False

# --- Personalization -------------------------------------------------------------
DEFAULT_RATING_SCALE = "ten"  # "ten" | "five_star" | "thumbs"
DEFAULT_DATE_FORMAT = "mdy"  # "mdy" | "dmy"
DEFAULT_LANDING_PAGE = "dashboard"  # a views.widgets.sidebar.NAV_ENTRIES key

# --- Privacy ----------------------------------------------------------------------
DEFAULT_CONFIRM_BEFORE_DELETE = True
DEFAULT_MASK_RATINGS = False
