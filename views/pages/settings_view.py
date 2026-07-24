from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWidgets import QComboBox

from settings.config import AppConfig
from settings.defaults import (
    DEFAULT_ACCENT,
    DEFAULT_ACHIEVEMENT_SOUND_ENABLED,
    DEFAULT_ANIMATIONS_ENABLED,
    DEFAULT_ENABLE_TRAILER_EMBED,
    DEFAULT_AUTO_BACKUP_ENABLED,
    DEFAULT_AUTO_BACKUP_INTERVAL_DAYS,
    DEFAULT_AUTO_BACKUP_RETENTION_COUNT,
    DEFAULT_CACHE_SIZE_LIMIT_MB,
    DEFAULT_CONFIRM_BEFORE_DELETE,
    DEFAULT_DATE_FORMAT,
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
from views import image_loader
from views.formatting import format_short_date
from views.pages.library_view import VIEW_MODES, SORT_PRESETS
from views.styles import AVAILABLE_THEMES
from views.widgets.sidebar import NAV_ENTRIES

_BACKUP_PATH_ROLE = Qt.ItemDataRole.UserRole
_SAGA_KEY_ROLE = Qt.ItemDataRole.UserRole

_VIEW_MODE_LABELS = {
    "grid": "Grid",
    "poster": "Poster",
    "list": "List",
    "compact": "Compact",
}

_TMDB_AUTO_SYNC_INTERVAL_OPTIONS = [
    ("Never (only the first-launch sync)", 0),
    ("Every 7 days", 7),
    ("Every 14 days", 14),
    ("Every 30 days", 30),
]

_RATING_SCALE_OPTIONS = [
    ("0–10 (e.g. 8.5)", "ten"),
    ("5-star (e.g. 4.3 ★)", "five_star"),
    ("Thumbs up/down", "thumbs"),
]

_DATE_FORMAT_OPTIONS = [
    ("MM/DD/YYYY (e.g. July 23, 2026)", "mdy"),
    ("DD/MM/YYYY (e.g. 23 July 2026)", "dmy"),
]

# page_key order mirrors views.main_window._build_ui's _add_page() calls
# (dashboard, library, timeline, collections, achievements, settings, in
# that order) -- there's no shared constant for that mapping to import, so
# this list is the one place that order is duplicated. Labels themselves
# come from NAV_ENTRIES so they can't drift from the sidebar's own wording.
_LANDING_PAGE_KEYS = ["dashboard", "library", "timeline", "collections", "achievements", "settings"]
_LANDING_PAGE_OPTIONS = [
    (key, NAV_ENTRIES[i][1]) for i, key in enumerate(_LANDING_PAGE_KEYS)
]

# Every field a "Reset All Settings to Default" click resets, paired with
# its default value. Deliberately excludes things that are *state* rather
# than a user preference -- application_name/data_directory/
# cache_directory/log_directory (paths), tmdb_api_key/
# tmdb_auto_sync_attempted/tmdb_last_synced_at (your key and sync
# history), auto_backup_last_run_at (backup history), and window_geometry
# (just where the window happens to be) all survive a settings reset.
_RESETTABLE_FIELDS: list[tuple[str, object]] = [
    ("theme", DEFAULT_THEME),
    ("accent_color", DEFAULT_ACCENT),
    ("library_default_view_mode", DEFAULT_LIBRARY_VIEW_MODE),
    ("library_default_sort_field", DEFAULT_LIBRARY_SORT_FIELD),
    ("library_default_sort_direction", DEFAULT_LIBRARY_SORT_DIRECTION),
    ("library_default_page_size", DEFAULT_LIBRARY_PAGE_SIZE),
    ("library_show_upcoming", DEFAULT_LIBRARY_SHOW_UPCOMING),
    ("timeline_default_sort_mode", DEFAULT_TIMELINE_SORT_MODE),
    ("timeline_excluded_sagas", list(DEFAULT_TIMELINE_EXCLUDED_SAGAS)),
    ("font_scale", DEFAULT_FONT_SCALE),
    ("poster_card_size", DEFAULT_POSTER_CARD_SIZE),
    ("animations_enabled", DEFAULT_ANIMATIONS_ENABLED),
    ("enable_trailer_embed", DEFAULT_ENABLE_TRAILER_EMBED),
    ("cache_size_limit_mb", DEFAULT_CACHE_SIZE_LIMIT_MB),
    ("tmdb_auto_sync_interval_days", DEFAULT_TMDB_AUTO_SYNC_INTERVAL_DAYS),
    ("auto_backup_enabled", DEFAULT_AUTO_BACKUP_ENABLED),
    ("auto_backup_interval_days", DEFAULT_AUTO_BACKUP_INTERVAL_DAYS),
    ("auto_backup_retention_count", DEFAULT_AUTO_BACKUP_RETENTION_COUNT),
    ("notify_achievement_unlocks", DEFAULT_NOTIFY_ACHIEVEMENT_UNLOCKS),
    ("notify_status_messages", DEFAULT_NOTIFY_STATUS_MESSAGES),
    ("achievement_sound_enabled", DEFAULT_ACHIEVEMENT_SOUND_ENABLED),
    ("rating_scale", DEFAULT_RATING_SCALE),
    ("date_format", DEFAULT_DATE_FORMAT),
    ("default_landing_page", DEFAULT_LANDING_PAGE),
    ("confirm_before_delete", DEFAULT_CONFIRM_BEFORE_DELETE),
    ("mask_ratings", DEFAULT_MASK_RATINGS),
]


class SettingsView(QWidget):
    """The Settings page.

    Unlike every other page (which only ever sees duck-typed, read-only
    objects from the services layer), SettingsView is handed the real,
    live ``AppConfig`` instance -- the same one ``ApplicationController``
    holds -- because application settings *are* config, not
    database-backed data.

    Every preference control auto-saves the instant it changes -- a
    combo box on currentIndexChanged, a checkbox on toggled, a spin box
    on valueChanged, the API key field on editingFinished (so it commits
    when you tab away or press Enter, not on every keystroke) -- there's
    no separate "Save" button anywhere on this page to click first.
    Genuine *actions* (Sync Now, Create/Restore/Delete Backup, Export/
    Import, Clear Cache) still are buttons, since those aren't settings
    to persist, they're one-off things to *do*.

    Triggering an actual TMDB sync -- and creating, restoring, or
    deleting a backup, or exporting/importing personal data -- is
    different: those are all service-layer/database calls, so this view
    still follows the "views never touch services/database directly"
    rule for them -- it only emits signals and waits for the controller
    to call back into the relevant ``set_*`` method. Choosing *where* a
    file goes (via native save/open dialogs) is presentation, though, so
    this view does own the ``QFileDialog`` calls for export and import,
    same as it owns the API key text field and the accent color picker.

    ``appearance_changed`` fires for theme/accent/font scale/poster card
    size/animations -- purely presentational, no database involved, so
    it's handled entirely by MainWindow and never reaches
    ApplicationController. Every other panel's changes go through
    ``preferences_changed`` instead, since those can affect data
    currently on screen (rating_scale, mask_ratings,
    timeline_excluded_sagas, ...), so the controller responds by
    refreshing whatever's currently visible.
    """

    tmdb_api_key_changed = Signal(str)
    tmdb_sync_requested = Signal()
    backup_requested = Signal()
    restore_requested = Signal(str)  # backup file path
    delete_backup_requested = Signal(str)  # backup file path
    export_requested = Signal(str)  # destination file path
    import_requested = Signal(str)  # source file path
    appearance_changed = Signal()
    # Emitted whenever any of the Library & Browsing / Timeline /
    # Notifications / Personalization / Privacy / Data & Sync panels
    # change. Unlike appearance_changed, this can affect data currently
    # on screen (e.g. rating_scale, mask_ratings, timeline_excluded_sagas),
    # so the controller responds by refreshing whatever's currently
    # visible.
    preferences_changed = Signal()
    check_for_updates_requested = Signal()
    install_update_requested = Signal()

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self._saga_options: list[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 20)
        outer.setSpacing(12)

        heading = QLabel("Settings")
        heading.setObjectName("pageHeading")

        subtitle = QLabel("Customize MarvelVerse Tracker. Changes save automatically.")
        subtitle.setObjectName("pageSubtitle")

        outer.addWidget(heading)
        outer.addWidget(subtitle)

        # Ten panels' worth of content is comfortably taller than most
        # window heights, so (like Project Details, the other
        # long/growing page) everything below the header lives inside a
        # scroll area rather than directly in this page's own layout.
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("settingsScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self.scroll_area, 1)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 4, 20)
        layout.setSpacing(20)

        layout.addWidget(self._build_reset_all_panel())
        layout.addWidget(self._build_updates_panel())
        layout.addWidget(self._build_appearance_panel())
        layout.addWidget(self._build_library_panel())
        layout.addWidget(self._build_timeline_panel())
        layout.addWidget(self._build_tmdb_panel())
        layout.addWidget(self._build_storage_panel())
        layout.addWidget(self._build_backups_panel())
        layout.addWidget(self._build_notifications_panel())
        layout.addWidget(self._build_personalization_panel())
        layout.addWidget(self._build_privacy_panel())
        layout.addWidget(self._build_import_export_panel())
        layout.addWidget(self._build_about_panel())
        layout.addStretch(1)

        self.scroll_area.setWidget(content)

    # --- construction helpers ------------------------------------------------

    def _build_reset_all_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(12)

        title = QLabel("Reset")
        title.setObjectName("sectionHeading")
        panel_layout.addWidget(title)

        description = QLabel(
            "Puts every setting on this page back to how MarvelVerse Tracker "
            "looked and behaved the first time you opened it. Doesn't touch "
            "your library, ratings, watch history, achievements, collections, "
            "backups, or TMDB API key -- only these preferences."
        )
        description.setObjectName("emptyState")
        description.setWordWrap(True)
        panel_layout.addWidget(description)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self.reset_all_button = QPushButton("Reset All Settings to Default")
        self.reset_all_button.setObjectName("secondaryButton")
        self.reset_all_button.clicked.connect(self._on_reset_all_clicked)
        button_row.addWidget(self.reset_all_button)
        button_row.addStretch()
        panel_layout.addLayout(button_row)

        self.reset_all_status_label = QLabel("")
        self.reset_all_status_label.setObjectName("statSubtitle")
        panel_layout.addWidget(self.reset_all_status_label)

        return panel

    def _build_updates_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(12)

        title = QLabel("Updates")
        title.setObjectName("sectionHeading")
        panel_layout.addWidget(title)

        from version import APP_VERSION

        self.current_version_label = QLabel(f"You're running version {APP_VERSION}.")
        self.current_version_label.setObjectName("emptyState")
        panel_layout.addWidget(self.current_version_label)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self.check_updates_button = QPushButton("Check for Updates")
        self.check_updates_button.setObjectName("secondaryButton")
        self.check_updates_button.clicked.connect(self.check_for_updates_requested.emit)
        button_row.addWidget(self.check_updates_button)

        self.download_install_button = QPushButton("Download && Install Update")
        self.download_install_button.setObjectName("primaryButton")
        self.download_install_button.clicked.connect(self.install_update_requested.emit)
        self.download_install_button.hide()
        button_row.addWidget(self.download_install_button)

        button_row.addStretch()
        panel_layout.addLayout(button_row)

        self.update_status_label = QLabel("")
        self.update_status_label.setObjectName("statSubtitle")
        self.update_status_label.setWordWrap(True)
        panel_layout.addWidget(self.update_status_label)

        self.update_release_notes_label = QLabel("")
        self.update_release_notes_label.setObjectName("statSubtitle")
        self.update_release_notes_label.setWordWrap(True)
        self.update_release_notes_label.hide()
        panel_layout.addWidget(self.update_release_notes_label)

        return panel

    def _build_appearance_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(12)

        title = QLabel("Appearance")
        title.setObjectName("sectionHeading")
        panel_layout.addWidget(title)

        description = QLabel("Choose a theme and an accent color. Changes preview immediately.")
        description.setObjectName("emptyState")
        description.setWordWrap(True)
        panel_layout.addWidget(description)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(12)

        theme_label = QLabel("Theme:")
        theme_label.setObjectName("inlineLabel")
        theme_label.setFixedWidth(90)
        theme_row.addWidget(theme_label)

        self.theme_combo = QComboBox()
        self.theme_combo.setObjectName("filterCombo")
        # Belt-and-suspenders alongside the QSS min-width/min-height: some
        # native platform styles size a QComboBox from its content/font
        # metrics before the stylesheet is applied, which is what made
        # this control render as a tall, squished, empty-looking pill.
        # Setting explicit sizes here is honored by the layout regardless
        # of style/platform.
        self.theme_combo.setMinimumWidth(200)
        self.theme_combo.setFixedHeight(36)
        for theme_key, theme_label_text in AVAILABLE_THEMES:
            self.theme_combo.addItem(theme_label_text, theme_key)
        current_theme_index = self.theme_combo.findData(self.config.theme)
        self.theme_combo.setCurrentIndex(current_theme_index if current_theme_index >= 0 else 0)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch()
        panel_layout.addLayout(theme_row)

        accent_row = QHBoxLayout()
        accent_row.setSpacing(12)

        accent_label = QLabel("Accent Color:")
        accent_label.setObjectName("inlineLabel")
        accent_label.setFixedWidth(90)
        accent_row.addWidget(accent_label)

        self.accent_swatch_button = QPushButton()
        self.accent_swatch_button.setObjectName("colorSwatchButton")
        self.accent_swatch_button.setFixedSize(32, 32)
        self.accent_swatch_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.accent_swatch_button.clicked.connect(self._on_choose_accent_clicked)
        accent_row.addWidget(self.accent_swatch_button)

        self.accent_hex_label = QLabel()
        self.accent_hex_label.setObjectName("statSubtitle")
        accent_row.addWidget(self.accent_hex_label)
        accent_row.addStretch()
        panel_layout.addLayout(accent_row)

        self._update_accent_swatch(self.config.accent_color or DEFAULT_ACCENT)

        font_row = QHBoxLayout()
        font_row.setSpacing(12)
        font_label = QLabel("Font Size:")
        font_label.setObjectName("inlineLabel")
        font_label.setFixedWidth(120)
        font_row.addWidget(font_label)

        self.font_scale_spin = QSpinBox()
        self.font_scale_spin.setObjectName("preferenceSpin")
        self.font_scale_spin.setRange(80, 150)
        self.font_scale_spin.setSingleStep(5)
        self.font_scale_spin.setSuffix("%")
        self.font_scale_spin.setFixedWidth(90)
        self.font_scale_spin.setFixedHeight(36)
        self.font_scale_spin.setValue(round(self.config.font_scale * 100))
        self.font_scale_spin.valueChanged.connect(self._commit_appearance_settings)
        font_row.addWidget(self.font_scale_spin)
        font_row.addStretch()
        panel_layout.addLayout(font_row)

        poster_size_row = QHBoxLayout()
        poster_size_row.setSpacing(12)
        poster_size_label = QLabel("Poster Card Size:")
        poster_size_label.setObjectName("inlineLabel")
        poster_size_label.setFixedWidth(120)
        poster_size_row.addWidget(poster_size_label)

        self.poster_card_size_spin = QSpinBox()
        self.poster_card_size_spin.setObjectName("preferenceSpin")
        self.poster_card_size_spin.setRange(100, 240)
        self.poster_card_size_spin.setSingleStep(10)
        self.poster_card_size_spin.setSuffix(" px")
        self.poster_card_size_spin.setFixedWidth(100)
        self.poster_card_size_spin.setFixedHeight(36)
        self.poster_card_size_spin.setValue(self.config.poster_card_size)
        self.poster_card_size_spin.valueChanged.connect(self._commit_appearance_settings)
        poster_size_row.addWidget(self.poster_card_size_spin)
        poster_size_row.addStretch()
        panel_layout.addLayout(poster_size_row)

        self.animations_enabled_checkbox = QCheckBox("Enable interface animations (page transitions)")
        self.animations_enabled_checkbox.setObjectName("preferenceCheckbox")
        self.animations_enabled_checkbox.setChecked(self.config.animations_enabled)
        self.animations_enabled_checkbox.toggled.connect(self._commit_appearance_settings)
        panel_layout.addWidget(self.animations_enabled_checkbox)

        self.trailer_embed_checkbox = QCheckBox(
            "Show a clickable trailer preview on Project Details"
        )
        self.trailer_embed_checkbox.setObjectName("preferenceCheckbox")
        self.trailer_embed_checkbox.setChecked(self.config.enable_trailer_embed)
        self.trailer_embed_checkbox.toggled.connect(self._commit_appearance_settings)
        panel_layout.addWidget(self.trailer_embed_checkbox)

        trailer_embed_note = QLabel(
            "Off by default. Embedding video needs a heavyweight browser "
            "component that can occasionally fail to start depending on "
            "your graphics drivers -- the \"Watch Trailer\" button on "
            "Project Details always works regardless of this setting."
        )
        trailer_embed_note.setObjectName("statSubtitle")
        trailer_embed_note.setWordWrap(True)
        panel_layout.addWidget(trailer_embed_note)

        self.appearance_status_label = QLabel("")
        self.appearance_status_label.setObjectName("statSubtitle")
        panel_layout.addWidget(self.appearance_status_label)

        return panel

    def _build_library_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(12)

        title = QLabel("Library & Browsing")
        title.setObjectName("sectionHeading")
        panel_layout.addWidget(title)

        description = QLabel(
            "Choose what the Library looks like and how it's sorted the "
            "moment you open it."
        )
        description.setObjectName("emptyState")
        description.setWordWrap(True)
        panel_layout.addWidget(description)

        view_row = QHBoxLayout()
        view_row.setSpacing(12)
        view_label = QLabel("Default View:")
        view_label.setObjectName("inlineLabel")
        view_label.setFixedWidth(140)
        view_row.addWidget(view_label)

        self.library_view_mode_combo = QComboBox()
        self.library_view_mode_combo.setObjectName("filterCombo")
        self.library_view_mode_combo.setMinimumWidth(200)
        self.library_view_mode_combo.setFixedHeight(36)
        for mode in VIEW_MODES:
            self.library_view_mode_combo.addItem(_VIEW_MODE_LABELS[mode], mode)
        view_row.addWidget(self.library_view_mode_combo)
        view_row.addStretch()
        panel_layout.addLayout(view_row)

        sort_row = QHBoxLayout()
        sort_row.setSpacing(12)
        sort_label = QLabel("Default Sort:")
        sort_label.setObjectName("inlineLabel")
        sort_label.setFixedWidth(140)
        sort_row.addWidget(sort_label)

        self.library_sort_combo = QComboBox()
        self.library_sort_combo.setObjectName("filterCombo")
        self.library_sort_combo.setMinimumWidth(200)
        self.library_sort_combo.setFixedHeight(36)
        for label, _field, _direction in SORT_PRESETS:
            self.library_sort_combo.addItem(label)
        sort_row.addWidget(self.library_sort_combo)
        sort_row.addStretch()
        panel_layout.addLayout(sort_row)

        page_size_row = QHBoxLayout()
        page_size_row.setSpacing(12)
        page_size_label = QLabel("Page Size:")
        page_size_label.setObjectName("inlineLabel")
        page_size_label.setFixedWidth(140)
        page_size_row.addWidget(page_size_label)

        self.library_page_size_spin = QSpinBox()
        self.library_page_size_spin.setObjectName("preferenceSpin")
        self.library_page_size_spin.setRange(6, 100)
        self.library_page_size_spin.setSingleStep(6)
        self.library_page_size_spin.setFixedWidth(90)
        self.library_page_size_spin.setFixedHeight(36)
        page_size_row.addWidget(self.library_page_size_spin)
        page_size_row.addStretch()
        panel_layout.addLayout(page_size_row)

        self.library_show_upcoming_checkbox = QCheckBox("Show upcoming/announced projects by default")
        self.library_show_upcoming_checkbox.setObjectName("preferenceCheckbox")
        panel_layout.addWidget(self.library_show_upcoming_checkbox)

        self._load_library_panel_from_config()

        # Connected after loading current values so restoring them above
        # doesn't immediately re-trigger a save of the same values.
        self.library_view_mode_combo.currentIndexChanged.connect(self._commit_library_settings)
        self.library_sort_combo.currentIndexChanged.connect(self._commit_library_settings)
        self.library_page_size_spin.valueChanged.connect(self._commit_library_settings)
        self.library_show_upcoming_checkbox.toggled.connect(self._commit_library_settings)

        self.library_status_label = QLabel("")
        self.library_status_label.setObjectName("statSubtitle")
        panel_layout.addWidget(self.library_status_label)

        return panel

    def _load_library_panel_from_config(self) -> None:
        view_index = self.library_view_mode_combo.findData(self.config.library_default_view_mode)
        self.library_view_mode_combo.setCurrentIndex(view_index if view_index >= 0 else 0)

        sort_index = next(
            (
                i
                for i, (_label, field, direction) in enumerate(SORT_PRESETS)
                if field == self.config.library_default_sort_field
                and direction == self.config.library_default_sort_direction
            ),
            0,
        )
        self.library_sort_combo.setCurrentIndex(sort_index)
        self.library_page_size_spin.setValue(self.config.library_default_page_size)
        self.library_show_upcoming_checkbox.setChecked(self.config.library_show_upcoming)

    def _build_timeline_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(12)

        title = QLabel("Timeline")
        title.setObjectName("sectionHeading")
        panel_layout.addWidget(title)

        description = QLabel(
            "Choose the Timeline's default sort, and which sagas to leave "
            "out of Chronological order (they'll still show up under "
            "Phase sorting)."
        )
        description.setObjectName("emptyState")
        description.setWordWrap(True)
        panel_layout.addWidget(description)

        sort_row = QHBoxLayout()
        sort_row.setSpacing(12)
        sort_label = QLabel("Default Sort:")
        sort_label.setObjectName("inlineLabel")
        sort_label.setFixedWidth(140)
        sort_row.addWidget(sort_label)

        self.timeline_sort_mode_combo = QComboBox()
        self.timeline_sort_mode_combo.setObjectName("filterCombo")
        self.timeline_sort_mode_combo.setMinimumWidth(200)
        self.timeline_sort_mode_combo.setFixedHeight(36)
        self.timeline_sort_mode_combo.addItem("Phase", "phase")
        self.timeline_sort_mode_combo.addItem("Chronological Order", "chronological")
        sort_row.addWidget(self.timeline_sort_mode_combo)
        sort_row.addStretch()
        panel_layout.addLayout(sort_row)

        excluded_label = QLabel("Exclude from Chronological Order:")
        excluded_label.setObjectName("inlineLabel")
        panel_layout.addWidget(excluded_label)

        self.timeline_excluded_sagas_list = QListWidget()
        self.timeline_excluded_sagas_list.setObjectName("backupsList")
        self.timeline_excluded_sagas_list.setFixedHeight(120)
        panel_layout.addWidget(self.timeline_excluded_sagas_list)

        self._load_timeline_panel_from_config()

        self.timeline_sort_mode_combo.currentIndexChanged.connect(self._commit_timeline_settings)
        self.timeline_excluded_sagas_list.itemChanged.connect(self._commit_timeline_settings)

        self.timeline_status_label = QLabel("")
        self.timeline_status_label.setObjectName("statSubtitle")
        panel_layout.addWidget(self.timeline_status_label)

        return panel

    def _load_timeline_panel_from_config(self) -> None:
        mode_index = self.timeline_sort_mode_combo.findData(self.config.timeline_default_sort_mode)
        self.timeline_sort_mode_combo.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        self._rebuild_saga_checklist()

    def _rebuild_saga_checklist(self) -> None:
        """Repopulate the saga checklist from self._saga_options (set via
        set_saga_options()), preserving which ones are currently checked
        in config.timeline_excluded_sagas. Safe to call before
        set_saga_options() has ever run -- the list is just empty until
        then, which is a fine (if uninformative) initial state for a
        freshly-built settings page. Signals are blocked while populating
        so this doesn't immediately fire _commit_timeline_settings for
        every item added."""
        self.timeline_excluded_sagas_list.blockSignals(True)
        try:
            self.timeline_excluded_sagas_list.clear()
            excluded = set(self.config.timeline_excluded_sagas)
            for saga in self._saga_options:
                item = QListWidgetItem(saga)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.CheckState.Checked if saga in excluded else Qt.CheckState.Unchecked
                )
                item.setData(_SAGA_KEY_ROLE, saga)
                self.timeline_excluded_sagas_list.addItem(item)
        finally:
            self.timeline_excluded_sagas_list.blockSignals(False)

    def set_saga_options(self, sagas: list[str]) -> None:
        """Populate the saga checklist from
        services.timeline_service.get_distinct_sagas(), called once by
        the controller at startup (this view never queries the database
        itself)."""
        self._saga_options = list(sagas)
        self._rebuild_saga_checklist()

    def _build_storage_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(12)

        title = QLabel("Data & Storage")
        title.setObjectName("sectionHeading")
        panel_layout.addWidget(title)

        description = QLabel(
            "Poster images are cached on disk so they don't have to be "
            "re-downloaded every time. Clearing the cache just means "
            "posters get downloaded again as needed -- your library and "
            "personal data aren't affected."
        )
        description.setObjectName("emptyState")
        description.setWordWrap(True)
        panel_layout.addWidget(description)

        self.cache_size_label = QLabel("")
        self.cache_size_label.setObjectName("statSubtitle")
        panel_layout.addWidget(self.cache_size_label)
        self._refresh_cache_size_label()

        limit_row = QHBoxLayout()
        limit_row.setSpacing(12)
        limit_label = QLabel("Cache Limit (MB):")
        limit_label.setObjectName("inlineLabel")
        limit_label.setFixedWidth(140)
        limit_row.addWidget(limit_label)

        self.cache_limit_spin = QSpinBox()
        self.cache_limit_spin.setObjectName("preferenceSpin")
        self.cache_limit_spin.setRange(50, 10000)
        self.cache_limit_spin.setSingleStep(50)
        self.cache_limit_spin.setFixedWidth(100)
        self.cache_limit_spin.setFixedHeight(36)
        self.cache_limit_spin.setValue(self.config.cache_size_limit_mb)
        self.cache_limit_spin.valueChanged.connect(self._commit_storage_settings)
        limit_row.addWidget(self.cache_limit_spin)
        limit_row.addStretch()
        panel_layout.addLayout(limit_row)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self.clear_cache_button = QPushButton("Clear Poster Cache")
        self.clear_cache_button.setObjectName("secondaryButton")
        self.clear_cache_button.clicked.connect(self._on_clear_cache_clicked)
        button_row.addWidget(self.clear_cache_button)
        button_row.addStretch()
        panel_layout.addLayout(button_row)

        self.storage_status_label = QLabel("")
        self.storage_status_label.setObjectName("statSubtitle")
        panel_layout.addWidget(self.storage_status_label)

        return panel

    def _refresh_cache_size_label(self) -> None:
        size_bytes = image_loader.cache_size_bytes()
        size_display = image_loader.format_cache_size(size_bytes)
        limit_mb = self.config.cache_size_limit_mb
        if size_bytes > limit_mb * 1024 * 1024:
            self.cache_size_label.setText(
                f"Poster cache: {size_display} used -- over your {limit_mb} MB limit. "
                "Consider clearing it below."
            )
        else:
            self.cache_size_label.setText(f"Poster cache: {size_display} used.")

    def _build_tmdb_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(12)

        title = QLabel("TMDB Integration")
        title.setObjectName("sectionHeading")
        panel_layout.addWidget(title)

        description = QLabel(
            "MarvelVerse Tracker uses The Movie Database (TMDB) to import "
            "and keep Marvel movies and TV series up to date. Get a free "
            "API key at themoviedb.org and paste it below -- it saves as "
            "soon as you press Enter or click away."
        )
        description.setObjectName("emptyState")
        description.setWordWrap(True)
        panel_layout.addWidget(description)

        key_row = QHBoxLayout()
        key_row.setSpacing(10)

        key_label = QLabel("API Key:")
        key_label.setObjectName("inlineLabel")

        self.api_key_input = QLineEdit()
        self.api_key_input.setObjectName("searchBox")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Paste your TMDB API key")
        if self.config.tmdb_api_key:
            self.api_key_input.setText(self.config.tmdb_api_key)
        self.api_key_input.editingFinished.connect(self._on_api_key_committed)

        key_row.addWidget(key_label)
        key_row.addWidget(self.api_key_input, 1)
        panel_layout.addLayout(key_row)

        env_note = QLabel(
            "A TMDB_API_KEY environment variable, if set, always takes "
            "priority over the key saved here."
        )
        env_note.setObjectName("statSubtitle")
        env_note.setWordWrap(True)
        panel_layout.addWidget(env_note)

        sync_row = QHBoxLayout()
        sync_row.setSpacing(10)

        self.sync_button = QPushButton("Sync from TMDB")
        self.sync_button.setObjectName("primaryButton")
        self.sync_button.clicked.connect(self.tmdb_sync_requested.emit)
        sync_row.addWidget(self.sync_button)

        self.sync_status_label = QLabel("")
        self.sync_status_label.setObjectName("statSubtitle")
        sync_row.addWidget(self.sync_status_label, 1)

        panel_layout.addLayout(sync_row)

        interval_row = QHBoxLayout()
        interval_row.setSpacing(12)
        interval_label = QLabel("Auto-Sync:")
        interval_label.setObjectName("inlineLabel")
        interval_label.setFixedWidth(90)
        interval_row.addWidget(interval_label)

        self.tmdb_auto_sync_combo = QComboBox()
        self.tmdb_auto_sync_combo.setObjectName("filterCombo")
        self.tmdb_auto_sync_combo.setMinimumWidth(240)
        self.tmdb_auto_sync_combo.setFixedHeight(36)
        for label, days in _TMDB_AUTO_SYNC_INTERVAL_OPTIONS:
            self.tmdb_auto_sync_combo.addItem(label, days)
        interval_index = self.tmdb_auto_sync_combo.findData(self.config.tmdb_auto_sync_interval_days)
        self.tmdb_auto_sync_combo.setCurrentIndex(interval_index if interval_index >= 0 else 0)
        self.tmdb_auto_sync_combo.currentIndexChanged.connect(self._commit_auto_sync_settings)
        interval_row.addWidget(self.tmdb_auto_sync_combo)
        interval_row.addStretch()
        panel_layout.addLayout(interval_row)

        return panel

    def _build_backups_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(12)

        title = QLabel("Backups")
        title.setObjectName("sectionHeading")
        panel_layout.addWidget(title)

        description = QLabel(
            "A backup is a full, point-in-time copy of your entire "
            "library and personal data. Restoring one replaces "
            "everything currently in the app with what's in the backup."
        )
        description.setObjectName("emptyState")
        description.setWordWrap(True)
        panel_layout.addWidget(description)

        self.backups_list = QListWidget()
        self.backups_list.setObjectName("backupsList")
        self.backups_list.setFixedHeight(140)
        self.backups_list.currentRowChanged.connect(self._on_backups_selection_changed)
        panel_layout.addWidget(self.backups_list)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self.create_backup_button = QPushButton("Create Backup Now")
        self.create_backup_button.setObjectName("secondaryButton")
        self.create_backup_button.clicked.connect(self.backup_requested.emit)
        button_row.addWidget(self.create_backup_button)

        self.restore_backup_button = QPushButton("Restore Selected")
        self.restore_backup_button.setObjectName("secondaryButton")
        self.restore_backup_button.setEnabled(False)
        self.restore_backup_button.clicked.connect(self._on_restore_clicked)
        button_row.addWidget(self.restore_backup_button)

        self.delete_backup_button = QPushButton("Delete Selected")
        self.delete_backup_button.setObjectName("secondaryButton")
        self.delete_backup_button.setEnabled(False)
        self.delete_backup_button.clicked.connect(self._on_delete_backup_clicked)
        button_row.addWidget(self.delete_backup_button)

        button_row.addStretch()
        panel_layout.addLayout(button_row)

        self.backup_status_label = QLabel("")
        self.backup_status_label.setObjectName("statSubtitle")
        panel_layout.addWidget(self.backup_status_label)

        self.auto_backup_checkbox = QCheckBox("Automatically create backups")
        self.auto_backup_checkbox.setObjectName("preferenceCheckbox")
        self.auto_backup_checkbox.setChecked(self.config.auto_backup_enabled)
        self.auto_backup_checkbox.toggled.connect(self._commit_auto_backup_settings)
        panel_layout.addWidget(self.auto_backup_checkbox)

        auto_row = QHBoxLayout()
        auto_row.setSpacing(12)

        interval_label = QLabel("Every")
        interval_label.setObjectName("inlineLabel")
        auto_row.addWidget(interval_label)
        self.auto_backup_interval_spin = QSpinBox()
        self.auto_backup_interval_spin.setObjectName("preferenceSpin")
        self.auto_backup_interval_spin.setRange(1, 90)
        self.auto_backup_interval_spin.setSuffix(" days")
        self.auto_backup_interval_spin.setFixedWidth(100)
        self.auto_backup_interval_spin.setFixedHeight(36)
        self.auto_backup_interval_spin.setValue(self.config.auto_backup_interval_days)
        self.auto_backup_interval_spin.valueChanged.connect(self._commit_auto_backup_settings)
        auto_row.addWidget(self.auto_backup_interval_spin)

        retention_label = QLabel("Keep last")
        retention_label.setObjectName("inlineLabel")
        auto_row.addWidget(retention_label)
        self.auto_backup_retention_spin = QSpinBox()
        self.auto_backup_retention_spin.setObjectName("preferenceSpin")
        self.auto_backup_retention_spin.setRange(1, 50)
        self.auto_backup_retention_spin.setSuffix(" backups")
        self.auto_backup_retention_spin.setFixedWidth(120)
        self.auto_backup_retention_spin.setFixedHeight(36)
        self.auto_backup_retention_spin.setValue(self.config.auto_backup_retention_count)
        self.auto_backup_retention_spin.valueChanged.connect(self._commit_auto_backup_settings)
        auto_row.addWidget(self.auto_backup_retention_spin)
        auto_row.addStretch()
        panel_layout.addLayout(auto_row)

        self.auto_backup_status_label = QLabel("")
        self.auto_backup_status_label.setObjectName("statSubtitle")
        panel_layout.addWidget(self.auto_backup_status_label)

        return panel

    def _build_notifications_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(12)

        title = QLabel("Notifications")
        title.setObjectName("sectionHeading")
        panel_layout.addWidget(title)

        description = QLabel("Choose which confirmations and alerts MarvelVerse Tracker shows you.")
        description.setObjectName("emptyState")
        description.setWordWrap(True)
        panel_layout.addWidget(description)

        self.notify_achievements_checkbox = QCheckBox("Show a notification when I unlock an achievement")
        self.notify_achievements_checkbox.setObjectName("preferenceCheckbox")
        self.notify_achievements_checkbox.setChecked(self.config.notify_achievement_unlocks)
        self.notify_achievements_checkbox.toggled.connect(self._commit_notifications_settings)
        panel_layout.addWidget(self.notify_achievements_checkbox)

        self.notify_status_checkbox = QCheckBox('Show "Saved"/"Logged" confirmations in the status bar')
        self.notify_status_checkbox.setObjectName("preferenceCheckbox")
        self.notify_status_checkbox.setChecked(self.config.notify_status_messages)
        self.notify_status_checkbox.toggled.connect(self._commit_notifications_settings)
        panel_layout.addWidget(self.notify_status_checkbox)

        self.achievement_sound_checkbox = QCheckBox("Play a sound when I unlock an achievement")
        self.achievement_sound_checkbox.setObjectName("preferenceCheckbox")
        self.achievement_sound_checkbox.setChecked(self.config.achievement_sound_enabled)
        self.achievement_sound_checkbox.toggled.connect(self._commit_notifications_settings)
        panel_layout.addWidget(self.achievement_sound_checkbox)

        self.notifications_status_label = QLabel("")
        self.notifications_status_label.setObjectName("statSubtitle")
        panel_layout.addWidget(self.notifications_status_label)

        return panel

    def _build_personalization_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(12)

        title = QLabel("Personalization")
        title.setObjectName("sectionHeading")
        panel_layout.addWidget(title)

        description = QLabel(
            "How ratings and dates are displayed throughout the app, and "
            "which page opens first at launch."
        )
        description.setObjectName("emptyState")
        description.setWordWrap(True)
        panel_layout.addWidget(description)

        rating_row = QHBoxLayout()
        rating_row.setSpacing(12)
        rating_label = QLabel("Rating Display:")
        rating_label.setObjectName("inlineLabel")
        rating_label.setFixedWidth(140)
        rating_row.addWidget(rating_label)
        self.rating_scale_combo = QComboBox()
        self.rating_scale_combo.setObjectName("filterCombo")
        self.rating_scale_combo.setMinimumWidth(240)
        self.rating_scale_combo.setFixedHeight(36)
        for label, value in _RATING_SCALE_OPTIONS:
            self.rating_scale_combo.addItem(label, value)
        rating_row.addWidget(self.rating_scale_combo)
        rating_row.addStretch()
        panel_layout.addLayout(rating_row)

        rating_note = QLabel(
            "This only changes how ratings are displayed (Timeline, "
            "Library, Dashboard) -- you still rate on a 0-10 scale on a "
            "project's own page."
        )
        rating_note.setObjectName("statSubtitle")
        rating_note.setWordWrap(True)
        panel_layout.addWidget(rating_note)

        date_row = QHBoxLayout()
        date_row.setSpacing(12)
        date_label = QLabel("Date Format:")
        date_label.setObjectName("inlineLabel")
        date_label.setFixedWidth(140)
        date_row.addWidget(date_label)
        self.date_format_combo = QComboBox()
        self.date_format_combo.setObjectName("filterCombo")
        self.date_format_combo.setMinimumWidth(240)
        self.date_format_combo.setFixedHeight(36)
        for label, value in _DATE_FORMAT_OPTIONS:
            self.date_format_combo.addItem(label, value)
        date_row.addWidget(self.date_format_combo)
        date_row.addStretch()
        panel_layout.addLayout(date_row)

        landing_row = QHBoxLayout()
        landing_row.setSpacing(12)
        landing_label = QLabel("Opening Page:")
        landing_label.setObjectName("inlineLabel")
        landing_label.setFixedWidth(140)
        landing_row.addWidget(landing_label)
        self.landing_page_combo = QComboBox()
        self.landing_page_combo.setObjectName("filterCombo")
        self.landing_page_combo.setMinimumWidth(240)
        self.landing_page_combo.setFixedHeight(36)
        for key, label in _LANDING_PAGE_OPTIONS:
            self.landing_page_combo.addItem(label, key)
        landing_row.addWidget(self.landing_page_combo)
        landing_row.addStretch()
        panel_layout.addLayout(landing_row)

        self._load_personalization_panel_from_config()

        self.rating_scale_combo.currentIndexChanged.connect(self._commit_personalization_settings)
        self.date_format_combo.currentIndexChanged.connect(self._commit_personalization_settings)
        self.landing_page_combo.currentIndexChanged.connect(self._commit_personalization_settings)

        self.personalization_status_label = QLabel("")
        self.personalization_status_label.setObjectName("statSubtitle")
        panel_layout.addWidget(self.personalization_status_label)

        return panel

    def _load_personalization_panel_from_config(self) -> None:
        rating_index = self.rating_scale_combo.findData(self.config.rating_scale)
        self.rating_scale_combo.setCurrentIndex(rating_index if rating_index >= 0 else 0)
        date_index = self.date_format_combo.findData(self.config.date_format)
        self.date_format_combo.setCurrentIndex(date_index if date_index >= 0 else 0)
        landing_index = self.landing_page_combo.findData(self.config.default_landing_page)
        self.landing_page_combo.setCurrentIndex(landing_index if landing_index >= 0 else 0)

    def _build_privacy_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(12)

        title = QLabel("Privacy")
        title.setObjectName("sectionHeading")
        panel_layout.addWidget(title)

        description = QLabel("Control what's confirmed before it's gone, and what's visible on screen.")
        description.setObjectName("emptyState")
        description.setWordWrap(True)
        panel_layout.addWidget(description)

        self.confirm_before_delete_checkbox = QCheckBox("Confirm before deleting a backup")
        self.confirm_before_delete_checkbox.setObjectName("preferenceCheckbox")
        self.confirm_before_delete_checkbox.setChecked(self.config.confirm_before_delete)
        self.confirm_before_delete_checkbox.toggled.connect(self._commit_privacy_settings)
        panel_layout.addWidget(self.confirm_before_delete_checkbox)

        self.mask_ratings_checkbox = QCheckBox(
            "Hide my ratings everywhere (Timeline, Library, Dashboard) -- handy when screen sharing"
        )
        self.mask_ratings_checkbox.setObjectName("preferenceCheckbox")
        self.mask_ratings_checkbox.setChecked(self.config.mask_ratings)
        self.mask_ratings_checkbox.toggled.connect(self._commit_privacy_settings)
        panel_layout.addWidget(self.mask_ratings_checkbox)

        self.privacy_status_label = QLabel("")
        self.privacy_status_label.setObjectName("statSubtitle")
        panel_layout.addWidget(self.privacy_status_label)

        return panel

    def _build_import_export_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(12)

        title = QLabel("Import / Export My Data")
        title.setObjectName("sectionHeading")
        panel_layout.addWidget(title)

        description = QLabel(
            "Export just your personal activity -- watched status, "
            "ratings, notes, watch history, and achievement progress -- "
            "as a portable file, separate from a full backup. Handy for "
            "moving to a new install: sync from TMDB first to rebuild "
            "the catalog, then import this to bring your activity with "
            "it."
        )
        description.setObjectName("emptyState")
        description.setWordWrap(True)
        panel_layout.addWidget(description)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self.export_button = QPushButton("Export My Data…")
        self.export_button.setObjectName("secondaryButton")
        self.export_button.clicked.connect(self._on_export_clicked)
        button_row.addWidget(self.export_button)

        self.import_button = QPushButton("Import My Data…")
        self.import_button.setObjectName("secondaryButton")
        self.import_button.clicked.connect(self._on_import_clicked)
        button_row.addWidget(self.import_button)

        button_row.addStretch()
        panel_layout.addLayout(button_row)

        self.import_export_status_label = QLabel("")
        self.import_export_status_label.setObjectName("statSubtitle")
        self.import_export_status_label.setWordWrap(True)
        panel_layout.addWidget(self.import_export_status_label)

        return panel

    def _build_about_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(16)

        title = QLabel("About")
        title.setObjectName("sectionHeading")
        panel_layout.addWidget(title)

        # --- Support -----------------------------------------------------------
        support_label = QLabel("SUPPORT")
        support_label.setObjectName("statTitle")
        panel_layout.addWidget(support_label)

        support_row = QHBoxLayout()
        support_row.setSpacing(10)

        self.about_github_button = QPushButton("View on GitHub")
        self.about_github_button.setObjectName("secondaryButton")
        self.about_github_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.about_github_button.clicked.connect(self._on_open_github_clicked)
        support_row.addWidget(self.about_github_button)

        self.about_discord_button = QPushButton("Join our Discord")
        self.about_discord_button.setObjectName("secondaryButton")
        self.about_discord_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.about_discord_button.clicked.connect(self._on_open_discord_clicked)
        support_row.addWidget(self.about_discord_button)

        self.about_report_bug_button = QPushButton("Report a Bug")
        self.about_report_bug_button.setObjectName("secondaryButton")
        self.about_report_bug_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.about_report_bug_button.clicked.connect(self._on_report_bug_clicked)
        support_row.addWidget(self.about_report_bug_button)

        support_row.addStretch()
        panel_layout.addLayout(support_row)

        # --- Donation ------------------------------------------------------------
        donation_label = QLabel("SUPPORT DEVELOPMENT")
        donation_label.setObjectName("statTitle")
        panel_layout.addWidget(donation_label)

        donation_row = QHBoxLayout()
        donation_row.setSpacing(10)

        self.about_donate_button = QPushButton("☕  Buy Me a Coffee")
        self.about_donate_button.setObjectName("primaryButton")
        self.about_donate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.about_donate_button.clicked.connect(self._on_open_donate_clicked)
        donation_row.addWidget(self.about_donate_button)

        donation_row.addStretch()
        panel_layout.addLayout(donation_row)

        # --- Resources -----------------------------------------------------------
        resources_label = QLabel("RESOURCES")
        resources_label.setObjectName("statTitle")
        panel_layout.addWidget(resources_label)

        resources_row = QHBoxLayout()
        resources_row.setSpacing(10)

        self.about_shortcuts_button = QPushButton("Keyboard Shortcuts")
        self.about_shortcuts_button.setObjectName("secondaryButton")
        self.about_shortcuts_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.about_shortcuts_button.clicked.connect(self._on_show_shortcuts_clicked)
        resources_row.addWidget(self.about_shortcuts_button)

        self.about_changelog_button = QPushButton("Changelog")
        self.about_changelog_button.setObjectName("secondaryButton")
        self.about_changelog_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.about_changelog_button.clicked.connect(self._on_open_changelog_clicked)
        resources_row.addWidget(self.about_changelog_button)

        resources_row.addStretch()
        panel_layout.addLayout(resources_row)

        # --- Diagnostics ---------------------------------------------------------
        diagnostics_label = QLabel("DIAGNOSTICS")
        diagnostics_label.setObjectName("statTitle")
        panel_layout.addWidget(diagnostics_label)

        diagnostics_row = QHBoxLayout()
        diagnostics_row.setSpacing(10)

        self.about_open_logs_button = QPushButton("Open Log Folder")
        self.about_open_logs_button.setObjectName("secondaryButton")
        self.about_open_logs_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.about_open_logs_button.clicked.connect(self._on_open_log_folder_clicked)
        diagnostics_row.addWidget(self.about_open_logs_button)

        self.about_copy_diagnostics_button = QPushButton("Copy Diagnostic Info")
        self.about_copy_diagnostics_button.setObjectName("secondaryButton")
        self.about_copy_diagnostics_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.about_copy_diagnostics_button.clicked.connect(self._on_copy_diagnostics_clicked)
        diagnostics_row.addWidget(self.about_copy_diagnostics_button)

        diagnostics_row.addStretch()
        panel_layout.addLayout(diagnostics_row)

        self.about_diagnostics_status_label = QLabel("")
        self.about_diagnostics_status_label.setObjectName("statSubtitle")
        panel_layout.addWidget(self.about_diagnostics_status_label)

        # --- Credits -------------------------------------------------------------
        credits_label = QLabel("CREDITS")
        credits_label.setObjectName("statTitle")
        panel_layout.addWidget(credits_label)

        credits_text = QLabel(
            "Built with <a href=\"https://doc.qt.io/qtforpython/\">PySide6</a> (Qt for "
            "Python), <a href=\"https://www.sqlalchemy.org/\">SQLAlchemy</a> and "
            "<a href=\"https://alembic.sqlalchemy.org/\">Alembic</a>, "
            "<a href=\"https://requests.readthedocs.io/\">Requests</a>, and "
            "<a href=\"https://python-pillow.org/\">Pillow</a>. Movie and TV data "
            "courtesy of <a href=\"https://www.themoviedb.org/\">The Movie Database "
            "(TMDB)</a>.<br><br>"
            "Thank you to everyone who's contributed code, bug reports, or ideas."
        )
        credits_text.setObjectName("statSubtitle")
        credits_text.setTextFormat(Qt.TextFormat.RichText)
        credits_text.setOpenExternalLinks(True)
        credits_text.setWordWrap(True)
        panel_layout.addWidget(credits_text)

        # --- Information ---------------------------------------------------------
        info_label = QLabel("INFORMATION")
        info_label.setObjectName("statTitle")
        panel_layout.addWidget(info_label)

        from version import APP_CREATED_DATE, APP_VERSION, APP_VERSION_DATE

        info_text = QLabel(
            f"<b>MarvelVerse Tracker</b><br>"
            f"Version {APP_VERSION} (released {APP_VERSION_DATE})<br>"
            f"Originally created {APP_CREATED_DATE}<br>"
            f"Licensed under the MIT License<br>"
            f"Movie/TV data provided by TMDB"
        )
        info_text.setObjectName("statSubtitle")
        info_text.setTextFormat(Qt.TextFormat.RichText)
        panel_layout.addWidget(info_text)

        disclaimer = QLabel(
            "MarvelVerse Tracker is an unofficial fan project and is not affiliated "
            "with, endorsed by, or sponsored by Marvel Entertainment, LLC or The "
            "Walt Disney Company."
        )
        disclaimer.setObjectName("emptyState")
        disclaimer.setWordWrap(True)
        panel_layout.addWidget(disclaimer)

        return panel

    def _on_open_github_clicked(self) -> None:
        from version import GITHUB_URL

        QDesktopServices.openUrl(QUrl(GITHUB_URL))

    def _on_open_discord_clicked(self) -> None:
        from version import DISCORD_INVITE_URL

        QDesktopServices.openUrl(QUrl(DISCORD_INVITE_URL))

    def _on_open_donate_clicked(self) -> None:
        from version import BUYMEACOFFEE_URL

        QDesktopServices.openUrl(QUrl(BUYMEACOFFEE_URL))

    def _on_report_bug_clicked(self) -> None:
        from version import GITHUB_URL

        QDesktopServices.openUrl(QUrl(f"{GITHUB_URL}/issues/new"))

    def _on_open_changelog_clicked(self) -> None:
        from version import GITHUB_URL

        QDesktopServices.openUrl(QUrl(f"{GITHUB_URL}/blob/main/CHANGELOG.md"))

    def _on_show_shortcuts_clicked(self) -> None:
        QMessageBox.information(
            self,
            "Keyboard Shortcuts",
            "<b>Library</b><br>"
            "Previous page: <b>A</b> or <b>Left Arrow</b><br>"
            "Next page: <b>D</b> or <b>Right Arrow</b><br>"
            "(These only apply while the Library page has focus, and only "
            "when a search box or other text field isn't currently being "
            "typed into.)",
        )

    def _on_open_log_folder_clicked(self) -> None:
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.config.log_directory)))
        if not opened:
            self.about_diagnostics_status_label.setText(
                f"Couldn't open a file browser -- logs are at: {self.config.log_directory}"
            )

    def _on_copy_diagnostics_clicked(self) -> None:
        import platform

        from PySide6.QtCore import qVersion
        from PySide6.QtGui import QGuiApplication

        from version import APP_VERSION

        try:
            db_size = self.config.database_file.stat().st_size
            db_size_display = f"{db_size / (1024 * 1024):.1f} MB"
        except OSError:
            db_size_display = "unknown"

        lines = [
            f"MarvelVerse Tracker {APP_VERSION}",
            f"OS: {platform.system()} {platform.release()} ({platform.machine()})",
            f"Python: {platform.python_version()}",
            f"Qt: {qVersion()}",
            f"Theme: {self.config.theme}",
            f"Database size: {db_size_display}",
        ]
        QGuiApplication.clipboard().setText("\n".join(lines))
        self.about_diagnostics_status_label.setText("Diagnostic info copied to clipboard.")

    # --- auto-save commit handlers -----------------------------------------------
    # Each of these is wired directly to the relevant controls' change
    # signals (see the _build_*_panel methods above) rather than to a
    # button click -- every setting on this page saves the instant it
    # changes.

    def _on_api_key_committed(self) -> None:
        key = self.api_key_input.text().strip()
        self.config.tmdb_api_key = key or None
        self.config.save()
        self.sync_status_label.setText("API key saved." if key else "API key cleared.")
        self.tmdb_api_key_changed.emit(key)

    def _commit_auto_sync_settings(self) -> None:
        self.config.tmdb_auto_sync_interval_days = self.tmdb_auto_sync_combo.currentData()
        self.config.save()
        self.sync_status_label.setText("Auto-sync schedule saved.")

    def _commit_library_settings(self) -> None:
        self.config.library_default_view_mode = self.library_view_mode_combo.currentData()
        _label, field, direction = SORT_PRESETS[self.library_sort_combo.currentIndex()]
        self.config.library_default_sort_field = field
        self.config.library_default_sort_direction = direction
        self.config.library_default_page_size = self.library_page_size_spin.value()
        self.config.library_show_upcoming = self.library_show_upcoming_checkbox.isChecked()
        self.config.save()
        self.library_status_label.setText("Saved.")
        self.preferences_changed.emit()

    def _commit_timeline_settings(self) -> None:
        self.config.timeline_default_sort_mode = self.timeline_sort_mode_combo.currentData()
        excluded = []
        for row in range(self.timeline_excluded_sagas_list.count()):
            item = self.timeline_excluded_sagas_list.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                excluded.append(item.data(_SAGA_KEY_ROLE))
        self.config.timeline_excluded_sagas = excluded
        self.config.save()
        self.timeline_status_label.setText("Saved.")
        self.preferences_changed.emit()

    def _commit_storage_settings(self) -> None:
        self.config.cache_size_limit_mb = self.cache_limit_spin.value()
        self.config.save()
        self.storage_status_label.setText("Saved.")
        self._refresh_cache_size_label()

    def _on_clear_cache_clicked(self) -> None:
        removed = image_loader.clear_cache()
        self.storage_status_label.setText(
            f"Cleared {removed} cached poster file{'s' if removed != 1 else ''}."
        )
        self._refresh_cache_size_label()

    def _commit_auto_backup_settings(self) -> None:
        self.config.auto_backup_enabled = self.auto_backup_checkbox.isChecked()
        self.config.auto_backup_interval_days = self.auto_backup_interval_spin.value()
        self.config.auto_backup_retention_count = self.auto_backup_retention_spin.value()
        self.config.save()
        self.auto_backup_status_label.setText("Saved.")

    def _commit_notifications_settings(self) -> None:
        self.config.notify_achievement_unlocks = self.notify_achievements_checkbox.isChecked()
        self.config.notify_status_messages = self.notify_status_checkbox.isChecked()
        self.config.achievement_sound_enabled = self.achievement_sound_checkbox.isChecked()
        self.config.save()
        self.notifications_status_label.setText("Saved.")
        self.preferences_changed.emit()

    def _commit_personalization_settings(self) -> None:
        self.config.rating_scale = self.rating_scale_combo.currentData()
        self.config.date_format = self.date_format_combo.currentData()
        self.config.default_landing_page = self.landing_page_combo.currentData()
        self.config.save()
        self.personalization_status_label.setText("Saved.")
        self.preferences_changed.emit()

    def _commit_privacy_settings(self) -> None:
        self.config.confirm_before_delete = self.confirm_before_delete_checkbox.isChecked()
        self.config.mask_ratings = self.mask_ratings_checkbox.isChecked()
        self.config.save()
        self.privacy_status_label.setText("Saved.")
        self.preferences_changed.emit()

    def _update_accent_swatch(self, hex_color: str) -> None:
        # Sets every visual property here, every time, rather than just
        # background -- an instance-level setStyleSheet() combined with
        # the app-level QSS rule for the same #colorSwatchButton selector
        # is what made this render as a distorted, oversized blob instead
        # of a clean 32x32 rounded square (some Qt/style combinations
        # don't reliably merge the two per-property the way a plain CSS
        # cascade would). Border color follows the active theme so the
        # swatch still reads correctly in both Dark and Light.
        border_color = "#30343D" if self.config.theme != "light" else "#D7DAE0"
        self.accent_swatch_button.setStyleSheet(
            "QPushButton#colorSwatchButton {"
            f"background: {hex_color};"
            f"border: 1px solid {border_color};"
            "border-radius: 6px;"
            "padding: 0px;"
            "margin: 0px;"
            "}"
        )
        self.accent_hex_label.setText(hex_color.upper())

    def _on_theme_changed(self, _index: int) -> None:
        theme_key = self.theme_combo.currentData()
        if theme_key is None or theme_key == self.config.theme:
            return
        self.config.theme = theme_key
        self.config.save()
        self._update_accent_swatch(self.config.accent_color or DEFAULT_ACCENT)
        self.appearance_status_label.setText("Saved.")
        self.appearance_changed.emit()

    def _on_choose_accent_clicked(self) -> None:
        initial = QColor(self.config.accent_color or DEFAULT_ACCENT)
        color = QColorDialog.getColor(initial, self, "Choose Accent Color")
        if not color.isValid():
            return

        hex_color = color.name().upper()
        self.config.accent_color = hex_color
        self.config.save()
        self._update_accent_swatch(hex_color)
        self.appearance_status_label.setText("Saved.")
        self.appearance_changed.emit()

    def _commit_appearance_settings(self, *_args) -> None:
        self.config.font_scale = self.font_scale_spin.value() / 100
        self.config.poster_card_size = self.poster_card_size_spin.value()
        self.config.animations_enabled = self.animations_enabled_checkbox.isChecked()
        self.config.enable_trailer_embed = self.trailer_embed_checkbox.isChecked()
        self.config.save()
        self.appearance_status_label.setText("Saved.")
        self.appearance_changed.emit()

    def _on_reset_all_clicked(self) -> None:
        confirmed = QMessageBox.question(
            self,
            "Reset All Settings",
            "Reset every setting on this page to its default?\n\n"
            "Your library, ratings, watch history, achievements, "
            "collections, backups, and TMDB API key are not affected -- "
            "only these preferences.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        for field_name, default_value in _RESETTABLE_FIELDS:
            setattr(self.config, field_name, default_value)
        self.config.save()

        self._reload_all_panels_from_config()

        self.reset_all_status_label.setText("All settings reset to default.")
        self.appearance_changed.emit()
        self.preferences_changed.emit()

    def _reload_all_panels_from_config(self) -> None:
        """Refresh every control on the page to reflect self.config as it
        currently stands -- used after Reset All Settings. Each control's
        own change signal is blocked while its value is being restored,
        so refreshing the UI doesn't itself trigger a redundant save (the
        values being set already match what's on disk)."""
        widgets_and_setters = [
            (self.theme_combo, lambda: self._set_combo_data(self.theme_combo, self.config.theme)),
            (self.font_scale_spin, lambda: self.font_scale_spin.setValue(round(self.config.font_scale * 100))),
            (self.poster_card_size_spin, lambda: self.poster_card_size_spin.setValue(self.config.poster_card_size)),
            (
                self.animations_enabled_checkbox,
                lambda: self.animations_enabled_checkbox.setChecked(self.config.animations_enabled),
            ),
            (
                self.trailer_embed_checkbox,
                lambda: self.trailer_embed_checkbox.setChecked(self.config.enable_trailer_embed),
            ),
            (self.library_view_mode_combo, self._load_library_panel_from_config),
            (self.timeline_sort_mode_combo, self._load_timeline_panel_from_config),
            (self.cache_limit_spin, lambda: self.cache_limit_spin.setValue(self.config.cache_size_limit_mb)),
            (
                self.tmdb_auto_sync_combo,
                lambda: self._set_combo_data(self.tmdb_auto_sync_combo, self.config.tmdb_auto_sync_interval_days),
            ),
            (
                self.auto_backup_checkbox,
                lambda: self.auto_backup_checkbox.setChecked(self.config.auto_backup_enabled),
            ),
            (
                self.auto_backup_interval_spin,
                lambda: self.auto_backup_interval_spin.setValue(self.config.auto_backup_interval_days),
            ),
            (
                self.auto_backup_retention_spin,
                lambda: self.auto_backup_retention_spin.setValue(self.config.auto_backup_retention_count),
            ),
            (
                self.notify_achievements_checkbox,
                lambda: self.notify_achievements_checkbox.setChecked(self.config.notify_achievement_unlocks),
            ),
            (
                self.notify_status_checkbox,
                lambda: self.notify_status_checkbox.setChecked(self.config.notify_status_messages),
            ),
            (
                self.achievement_sound_checkbox,
                lambda: self.achievement_sound_checkbox.setChecked(self.config.achievement_sound_enabled),
            ),
            (self.rating_scale_combo, self._load_personalization_panel_from_config),
            (
                self.confirm_before_delete_checkbox,
                lambda: self.confirm_before_delete_checkbox.setChecked(self.config.confirm_before_delete),
            ),
            (self.mask_ratings_checkbox, lambda: self.mask_ratings_checkbox.setChecked(self.config.mask_ratings)),
        ]
        for widget, apply in widgets_and_setters:
            widget.blockSignals(True)
            try:
                apply()
            finally:
                widget.blockSignals(False)

        self._update_accent_swatch(self.config.accent_color or DEFAULT_ACCENT)
        self._rebuild_saga_checklist()

    @staticmethod
    def _set_combo_data(combo: QComboBox, data) -> None:
        index = combo.findData(data)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _on_backups_selection_changed(self, row: int) -> None:
        has_selection = row >= 0
        self.restore_backup_button.setEnabled(has_selection)
        self.delete_backup_button.setEnabled(has_selection)

    def _on_restore_clicked(self) -> None:
        item = self.backups_list.currentItem()
        if item is None:
            return

        confirmed = QMessageBox.question(
            self,
            "Restore Backup",
            f"Restore \"{item.text()}\"?\n\n"
            "This replaces everything currently in the app -- your entire "
            "library and personal data -- with what's in this backup. "
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        self.restore_requested.emit(item.data(_BACKUP_PATH_ROLE))

    def _on_delete_backup_clicked(self) -> None:
        item = self.backups_list.currentItem()
        if item is None:
            return

        if self.config.confirm_before_delete:
            confirmed = QMessageBox.question(
                self,
                "Delete Backup",
                f"Delete \"{item.text()}\"? This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if confirmed != QMessageBox.StandardButton.Yes:
                return

        self.delete_backup_requested.emit(item.data(_BACKUP_PATH_ROLE))

    def _on_export_clicked(self) -> None:
        path, _selected_filter = QFileDialog.getSaveFileName(
            self, "Export My Data", "marvelverse-export.json", "JSON Files (*.json)"
        )
        if path:
            self.export_requested.emit(path)

    def _on_import_clicked(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self, "Import My Data", "", "JSON Files (*.json)"
        )
        if path:
            self.import_requested.emit(path)

    # --- controller-facing API ---------------------------------------------

    def set_sync_in_progress(self, in_progress: bool) -> None:
        """Disable the sync button and show a busy message while a sync
        runs. Sync currently runs synchronously on the UI thread (see
        ApplicationController._run_tmdb_sync) -- this at least stops a
        second click from queuing up a concurrent sync and gives the user
        feedback that something is happening."""
        self.sync_button.setEnabled(not in_progress)
        if in_progress:
            self.sync_status_label.setText("Syncing from TMDB…")

    def set_sync_status(self, message: str) -> None:
        self.sync_status_label.setText(message)

    def set_backups(self, backups) -> None:
        """Repopulate the backups list from a tuple of duck-typed
        services.backup_service.BackupInfo objects, newest first (as the
        service already sorts them). Clears the current selection, since
        whatever was selected may no longer be at the same row."""
        self.backups_list.clear()
        for backup in backups:
            timestamp = f"{format_short_date(backup.created_at)} {backup.created_at.strftime('%I:%M %p')}"
            item = QListWidgetItem(f"{backup.filename}  ·  {timestamp}  ·  {backup.size_display}")
            item.setData(_BACKUP_PATH_ROLE, str(backup.path))
            self.backups_list.addItem(item)
        self.restore_backup_button.setEnabled(False)
        self.delete_backup_button.setEnabled(False)

    def set_backup_status(self, message: str) -> None:
        self.backup_status_label.setText(message)

    def set_import_export_status(self, message: str) -> None:
        self.import_export_status_label.setText(message)

    def set_update_check_in_progress(self, in_progress: bool) -> None:
        self.check_updates_button.setEnabled(not in_progress)
        if in_progress:
            self.update_status_label.setText("Checking for updates…")

    def set_no_update_available(self) -> None:
        self.update_status_label.setText("You're on the latest version.")
        self.download_install_button.hide()
        self.update_release_notes_label.hide()

    def set_update_check_failed(self, message: str) -> None:
        self.update_status_label.setText(message)
        self.download_install_button.hide()
        self.update_release_notes_label.hide()

    def show_update_available(self, info, *, can_install: bool) -> None:
        """`info` is a duck-typed services.update_service.UpdateInfo.
        `can_install` reflects whether this is a packaged .exe (where
        apply_update_and_restart() actually applies) -- running from
        source, there's a newer version to know about but nothing this
        view can install, so it points at `git pull` instead of showing
        a button that would just fail."""
        self.update_status_label.setText(f"Version {info.version} is available.")
        if info.release_notes:
            self.update_release_notes_label.setText(info.release_notes)
            self.update_release_notes_label.show()
        else:
            self.update_release_notes_label.hide()

        if can_install:
            self.download_install_button.setText("Download && Install Update")
            self.download_install_button.setEnabled(True)
            self.download_install_button.show()
        else:
            self.download_install_button.hide()

    def set_update_install_in_progress(self, message: str) -> None:
        self.download_install_button.setEnabled(False)
        self.update_status_label.setText(message)

    def set_update_install_failed(self, message: str) -> None:
        self.download_install_button.setEnabled(True)
        self.update_status_label.setText(message)
