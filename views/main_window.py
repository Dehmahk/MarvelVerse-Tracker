from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, QEasingCurve, QPropertyAnimation, QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QSystemTrayIcon,
    QWidget,
)

from settings.config import AppConfig
from settings.defaults import DEFAULT_POSTER_CARD_SIZE
from resource_paths import resource_root
from views import image_loader
from views.font_scaling import apply_font_scale
from views.formatting import configure as configure_formatting
from views.pages.achievements_view import AchievementsView
from views.pages.calendar_view import CalendarView
from views.pages.collections_view import CollectionsView
from views.pages.dashboard_view import DashboardView
from views.pages.library_view import LibraryView
from views.pages.person_detail_view import PersonDetailView
from views.pages.project_detail_view import ProjectDetailView
from views.pages.settings_view import SettingsView
from views.pages.timeline_view import TimelineView
from views.styles import load_stylesheet
from views.widgets.sidebar import Sidebar
from views.widgets.toolbar import MainToolBar

logger = logging.getLogger(__name__)

# Fallback index for _detail_return_index (the sidebar's "Library" row),
# i.e. where the project detail page's Back button sends the user if
# something ever activates a project before the return index has been set.
_LIBRARY_NAV_INDEX = 1

# Sidebar row for each Settings > Personalization "Opening Page" choice --
# mirrors the order pages are added in _build_ui()/_add_page() below (and
# views.pages.settings_view._LANDING_PAGE_KEYS, which offers this same set
# of choices). Not derived from _page_keys because that dict isn't built
# until _build_ui() runs, and this is needed to seed the sidebar's initial
# row before _build_ui() gets that far.
_LANDING_PAGE_ROWS = {
    "dashboard": 0,
    "library": 1,
    "timeline": 2,
    "calendar": 3,
    "collections": 4,
    "achievements": 5,
    "settings": 6,
}


class MainWindow(QMainWindow):
    """The application shell. Composes the sidebar, toolbar, status bar, and
    page stack, and re-emits user actions as signals. Deliberately has no
    knowledge of the database or services — that stays in the controller,
    per the "views never directly access the database" architecture rule."""

    refresh_requested = Signal()
    search_changed = Signal(str)
    surprise_me_requested = Signal()
    project_activated = Signal(int)
    # Emitted from the Dashboard's Collections spotlight "View Collection"
    # button -- the controller responds by navigating to the Collections
    # page and selecting this collection there.
    collection_activated = Signal(int)
    user_data_field_changed = Signal(int, str, object)
    log_watch_requested = Signal(int, str)
    find_on_tmdb_requested = Signal(int)
    person_activated = Signal(int)
    episode_toggled = Signal(int, bool)
    season_toggled = Signal(int, int, bool)
    timeline_universe_changed = Signal(object)  # int | None
    timeline_sort_mode_changed = Signal(str)  # "phase" | "chronological"
    tmdb_api_key_changed = Signal(str)
    tmdb_sync_requested = Signal()
    backup_requested = Signal()
    check_for_updates_requested = Signal()
    run_data_integrity_check_requested = Signal()
    install_update_requested = Signal()
    restore_requested = Signal(str)
    delete_backup_requested = Signal(str)
    export_requested = Signal(str)
    import_requested = Signal(str)
    compare_with_friend_requested = Signal(str)
    # Emitted with a page key ("dashboard", "library", "timeline",
    # "collections", "achievements", "settings", "project_detail")
    # whenever the visible page changes -- lets the controller defer a
    # page's data refresh until it's actually on screen (see
    # current_page_key()/ApplicationController._on_page_changed) instead
    # of rebuilding hidden pages nobody can see.
    page_changed = Signal(str)
    # Emitted after any Library & Browsing/Timeline/Notifications/
    # Personalization/Privacy preference is saved (forwarded straight from
    # SettingsView.preferences_changed, after this window re-applies
    # rating/date formatting locally) -- tells the controller to refresh
    # whatever's currently visible so already-rendered pages pick up the
    # new preference immediately rather than only on next navigation.
    preferences_changed = Signal()

    def __init__(self, config: AppConfig) -> None:
        super().__init__()

        self.config = config
        self._animations_enabled = config.animations_enabled
        self._page_transition_animation = None
        self._tray_icon = None  # lazily created on first show_native_notification() call

        # Poster/backdrop art is downloaded once and cached to disk under
        # the configured cache directory; every PosterLabel across the app
        # (Library cards/rows, Timeline, Dashboard, Project Detail) pulls
        # from this one loader. Configured here, before any page is built,
        # so every widget that requests a poster below already has it.
        image_loader.configure(config.cache_directory)
        configure_formatting(
            date_format=config.date_format,
            rating_scale=config.rating_scale,
            mask_ratings=config.mask_ratings,
        )

        self.setWindowTitle(config.application_name)
        self.resize(1440, 900)
        self.setMinimumSize(QSize(1100, 700))
        self._restore_window_geometry()

        # Which sidebar-navigable page to return to when the project detail
        # page's Back button is pressed -- captured in show_project_detail()
        # from wherever a project was actually activated (Library, Dashboard,
        # or Timeline), so Back always goes "where you came from" instead of
        # hardcoding Library.
        self._detail_return_index = _LIBRARY_NAV_INDEX

        self._build_ui()
        self._load_theme()

    def _add_page(self, widget: QWidget, key: str) -> int:
        """Add `widget` to the page stack and remember its index -> key
        mapping for current_page_key(). Returns the index, same as
        QStackedWidget.addWidget(), so call sites that need it (the
        Project Detail page's index) don't have to look it up separately."""
        index = self.pages.addWidget(widget)
        self._page_keys[index] = key
        return index

    def _build_ui(self) -> None:
        self.toolbar = MainToolBar()
        self.toolbar.refresh_requested.connect(self.refresh_requested.emit)
        self.toolbar.search_changed.connect(self.search_changed.emit)
        self.toolbar.surprise_me_requested.connect(self.surprise_me_requested.emit)
        self.toolbar.sidebar_toggle_requested.connect(self._toggle_sidebar)
        self.addToolBar(self.toolbar)

        self.pages = QStackedWidget()
        # Populated by _add_page() below; lets current_page_key() answer
        # "which page is visible" in plain strings the controller can act
        # on, without it ever needing to know about QStackedWidget indices.
        self._page_keys: dict[int, str] = {}

        self.dashboard_view = DashboardView(accent_color=self.config.accent_color)
        self._add_page(self.dashboard_view, "dashboard")
        self.library_view = LibraryView(
            default_view_mode=self.config.library_default_view_mode,
            poster_size_scale=self.config.poster_card_size / DEFAULT_POSTER_CARD_SIZE,
        )
        self._add_page(self.library_view, "library")
        self.timeline_view = TimelineView()
        self._add_page(self.timeline_view, "timeline")
        self.calendar_view = CalendarView()
        self._add_page(self.calendar_view, "calendar")
        self.collections_view = CollectionsView()
        self._add_page(self.collections_view, "collections")
        self.achievements_view = AchievementsView()
        self._add_page(self.achievements_view, "achievements")
        self.settings_view = SettingsView(self.config)
        self._add_page(self.settings_view, "settings")

        # Project Details has no sidebar row -- it's only reached by
        # activating a project from the Library -- so it's appended after
        # the sidebar-navigable pages and shown via show_project_detail().
        self.project_detail_view = ProjectDetailView(enable_trailer_embed=self.config.enable_trailer_embed)
        self._detail_page_index = self._add_page(self.project_detail_view, "project_detail")

        # Actor/Director Details -- only reached from Project Details'
        # cast/crew list, same "no sidebar row, appended after the
        # sidebar-navigable pages" reasoning as Project Details itself.
        self.person_detail_view = PersonDetailView()
        self._person_detail_page_index = self._add_page(self.person_detail_view, "person_detail")

        self.library_view.project_activated.connect(self.project_activated.emit)
        self.dashboard_view.project_activated.connect(self.project_activated.emit)
        self.dashboard_view.collection_activated.connect(self.collection_activated.emit)
        self.timeline_view.project_activated.connect(self.project_activated.emit)
        self.collections_view.project_activated.connect(self.project_activated.emit)
        self.calendar_view.project_activated.connect(self.project_activated.emit)
        self.timeline_view.universe_changed.connect(self.timeline_universe_changed.emit)
        self.timeline_view.sort_mode_changed.connect(self.timeline_sort_mode_changed.emit)
        self.project_detail_view.back_requested.connect(self._on_back_requested)
        self.project_detail_view.navigate_to_project_requested.connect(self.project_activated.emit)
        self.project_detail_view.find_on_tmdb_requested.connect(self.find_on_tmdb_requested.emit)
        self.project_detail_view.user_data_field_changed.connect(
            self.user_data_field_changed.emit
        )
        self.project_detail_view.log_watch_requested.connect(self.log_watch_requested.emit)
        self.project_detail_view.person_activated.connect(self.person_activated.emit)
        self.project_detail_view.episode_toggled.connect(self.episode_toggled.emit)
        self.project_detail_view.season_toggled.connect(self.season_toggled.emit)
        self.person_detail_view.back_requested.connect(self._on_person_detail_back_requested)
        self.person_detail_view.project_activated.connect(self.project_activated.emit)
        self.settings_view.tmdb_api_key_changed.connect(self.tmdb_api_key_changed.emit)
        self.settings_view.tmdb_sync_requested.connect(self.tmdb_sync_requested.emit)
        self.settings_view.backup_requested.connect(self.backup_requested.emit)
        self.settings_view.check_for_updates_requested.connect(self.check_for_updates_requested.emit)
        self.settings_view.run_data_integrity_check_requested.connect(self.run_data_integrity_check_requested.emit)
        self.settings_view.install_update_requested.connect(self.install_update_requested.emit)
        self.settings_view.restore_requested.connect(self.restore_requested.emit)
        self.settings_view.delete_backup_requested.connect(self.delete_backup_requested.emit)
        self.settings_view.export_requested.connect(self.export_requested.emit)
        self.settings_view.import_requested.connect(self.import_requested.emit)
        self.settings_view.compare_with_friend_requested.connect(self.compare_with_friend_requested.emit)
        self.settings_view.appearance_changed.connect(self._on_appearance_changed)
        self.settings_view.preferences_changed.connect(self._on_preferences_changed)

        self.sidebar = Sidebar()
        # Seed the sidebar to the configured "Opening Page" (Settings >
        # Personalization) before wiring up navigate -- otherwise this
        # would fire _on_navigate mid-construction, against widgets
        # (toolbar, status bar) not fully wired yet.
        landing_row = _LANDING_PAGE_ROWS.get(self.config.default_landing_page, 0)
        if landing_row:
            self.sidebar.navigation.setCurrentRow(landing_row)
        self.sidebar.navigate.connect(self._on_navigate)

        self.splitter = QSplitter()
        self.splitter.setObjectName("shellSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.pages)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        self.setCentralWidget(self.splitter)

        self._build_status_bar()

        # Initialize toolbar title and status bar to match the default page.
        self._on_navigate(self.sidebar.navigation.currentRow())

    def _build_status_bar(self) -> None:
        status = QStatusBar()
        status.setObjectName("mainStatusBar")

        self.status_message = QLabel("Ready")
        status.addWidget(self.status_message, 1)

        self.status_projects_chip = QLabel("")
        self.status_projects_chip.setObjectName("statusChip")
        status.addPermanentWidget(self.status_projects_chip)

        self.status_watched_chip = QLabel("")
        self.status_watched_chip.setObjectName("statusChip")
        status.addPermanentWidget(self.status_watched_chip)

        self.status_db_chip = QLabel("● Database Connected")
        self.status_db_chip.setObjectName("statusChipOk")
        status.addPermanentWidget(self.status_db_chip)

        self.setStatusBar(status)

    def _on_navigate(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.toolbar.set_page_title(self.sidebar.page_title(index))
        self.page_changed.emit(self._page_keys.get(index, ""))
        self._animate_current_page()

    def _animate_current_page(self) -> None:
        """A brief fade-in for whichever page is now current -- gated on
        Settings > Appearance's "Enable interface animations" checkbox.
        Deliberately simple (opacity only, ~180ms) rather than a slide or
        scale: this is meant to soften an otherwise-instant page swap,
        not call attention to itself. The QGraphicsOpacityEffect and
        QPropertyAnimation are recreated per-call and parented to the
        page widget, so they're cleaned up automatically the next time
        this runs (or the widget is destroyed) rather than accumulating.
        """
        if not self._animations_enabled:
            return

        page = self.pages.currentWidget()
        if page is None:
            return

        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", page)
        animation.setDuration(180)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        # Keep a reference so it isn't garbage-collected mid-animation --
        # cleared, along with the opacity effect itself, once it finishes.
        self._page_transition_animation = animation
        animation.finished.connect(lambda: page.setGraphicsEffect(None))
        animation.start()

    def current_page_key(self) -> str | None:
        """The page currently on screen -- "dashboard", "library",
        "timeline", "collections", "achievements", "settings", or
        "project_detail" -- or None if somehow unset. Lets the controller
        decide whether a given page's data needs refreshing right now or
        can wait until the user actually navigates to it, without the
        controller needing any knowledge of QStackedWidget indices."""
        return self._page_keys.get(self.pages.currentIndex())

    def navigate_to_page(self, page_key: str) -> None:
        """Switch to whichever sidebar-navigable page matches `page_key`
        (e.g. "collections") -- lets the controller drive navigation
        (like the Dashboard's Collections spotlight "View Collection"
        button) without reaching into the sidebar/QStackedWidget
        internals itself. A no-op for an unrecognized key."""
        row = _LANDING_PAGE_ROWS.get(page_key)
        if row is not None:
            self.sidebar.navigation.setCurrentRow(row)

    def _on_back_requested(self) -> None:
        # Return to whichever sidebar-navigable page the project was
        # activated from (Library, Dashboard, or Timeline can all do it),
        # per _detail_return_index set in show_project_detail(). Not routed
        # through the sidebar's currentRowChanged signal: the sidebar's
        # selection never left that row while the detail page was showing,
        # so setCurrentRow(...) would be a no-op. Go through the same code
        # path _on_navigate uses instead.
        self._on_navigate(self._detail_return_index)

    def _on_person_detail_back_requested(self) -> None:
        # Person Details is only ever reached from Project Details' own
        # cast/crew list -- there's no other path to it in this app --
        # so Back always returns there directly, never all the way back
        # to Library/Dashboard/Timeline. Deliberately NOT routed through
        # _on_navigate (that's for sidebar-navigable pages only, and
        # Project Details isn't one); this mirrors show_project_detail's
        # own setCurrentIndex(...) call instead.
        self.pages.setCurrentIndex(self._detail_page_index)

    def _toggle_sidebar(self) -> None:
        self.sidebar.set_collapsed(not self.sidebar.is_collapsed())

    def _load_theme(self) -> None:
        self.setStyleSheet(load_stylesheet(self.config.theme, self.config.accent_color))

    def _on_appearance_changed(self) -> None:
        """SettingsView already wrote theme/accent_color/font_scale/
        poster_card_size/animations_enabled to AppConfig directly (the
        same live instance this window holds) -- this re-applies all of
        them immediately, with no restart and no controller/service
        involvement for the ones that are pure presentation. The one
        exception is poster_card_size: Library's already-rendered cards
        need an actual rebuild to pick up a new size, not just a stored
        value for next time, so this forwards to preferences_changed too
        (same "refresh whatever's currently visible" mechanism
        Personalization's rating_scale/date_format changes already use)."""
        self._load_theme()
        self.dashboard_view.set_accent_color(self.config.accent_color)
        apply_font_scale(QApplication.instance(), self.config.font_scale)
        self.library_view.set_poster_size_scale(self.config.poster_card_size / DEFAULT_POSTER_CARD_SIZE)
        self._animations_enabled = self.config.animations_enabled
        self.project_detail_view.set_trailer_embed_enabled(self.config.enable_trailer_embed)
        self.show_status_message("Appearance updated")
        self.preferences_changed.emit()

    def _on_preferences_changed(self) -> None:
        """Same "SettingsView already wrote it to the live AppConfig"
        pattern as _on_appearance_changed, but for rating_scale/
        date_format/mask_ratings specifically: re-apply them to the
        views.formatting singleton immediately, then forward the signal
        on to the controller so it can refresh whichever data pages are
        currently visible (Library/Timeline/Dashboard rows showing a
        rating or a date need to actually re-render to reflect the
        change -- re-configuring formatting alone doesn't repaint
        anything that isn't rebuilt)."""
        configure_formatting(
            date_format=self.config.date_format,
            rating_scale=self.config.rating_scale,
            mask_ratings=self.config.mask_ratings,
        )
        self.preferences_changed.emit()

    # --- controller-facing API ---------------------------------------------
    def _restore_window_geometry(self) -> None:
        """Restore the window to wherever/however big it was last closed
        (including maximized state), if we have that saved. Left at the
        1440x900 default (already set by the caller) on a fresh install,
        or if the saved blob is corrupt/from an incompatible Qt version --
        restoreGeometry() returns False rather than raising in that case,
        so this just quietly keeps the default instead of crashing."""
        if not self.config.window_geometry:
            return
        try:
            geometry = QByteArray.fromHex(self.config.window_geometry.encode("ascii"))
        except (ValueError, UnicodeEncodeError):
            return
        self.restoreGeometry(geometry)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Persist window geometry on the way out. Everything the user
        has actually done (ratings, watched flags, collections, ...) is
        already committed to disk the moment it happens (every services-
        layer write goes through session_scope(), which commits
        immediately) -- this is just the one piece of state (window
        size/position/maximized) that can only be captured right at
        close time.

        Disposing the database engine happens later, in
        ApplicationController's aboutToQuit handler rather than here --
        that needs to wait for any in-flight background TMDB sync to
        finish first (see TMDBSyncWorker), and this window has no
        reference to the controller or its worker thread to check."""
        self.config.window_geometry = bytes(self.saveGeometry().toHex()).decode("ascii")
        self.config.save()
        super().closeEvent(event)

    def show_update_prompt(self, version: str, release_notes: str) -> bool:
        """A modal popup shown once, right when a startup update check
        finds a newer version -- unlike the Settings page's own
        "Download & Install Update" button (still there either way, for
        anyone who dismisses this), this surfaces it immediately rather
        than only for someone who happens to open Settings later.
        Returns True for "Update Now", False for "Update Later" (which
        includes closing the dialog via the X button -- QMessageBox
        reports that the same as clicking whichever button isn't the
        default, so this treats it the same as an explicit "later")."""
        box = QMessageBox(self)
        box.setWindowTitle("Update Available")
        text = f"MarvelVerse Tracker {version} is available."
        if release_notes:
            # Release notes come from a GitHub Release body, which could
            # be long -- keep the popup itself short and let Settings'
            # own (scrollable) release-notes label carry the rest,
            # rather than growing this modal to fit an arbitrarily long
            # changelog.
            snippet = release_notes if len(release_notes) <= 280 else release_notes[:277] + "…"
            text += f"\n\n{snippet}"
        box.setText(text)
        update_now_button = box.addButton("Update Now", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Update Later", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(update_now_button)
        box.exec()
        return box.clickedButton() is update_now_button

    def show_status_message(self, message: str, timeout_ms: int = 4000) -> None:
        self.statusBar().showMessage(message, timeout_ms)

    def show_native_notification(self, title: str, message: str) -> None:
        """A real OS-level desktop notification (via the system tray),
        distinct from show_status_message()'s in-app status bar text --
        this shows up outside the app window entirely, the same way any
        other desktop notification would, so it's visible even if the
        app isn't currently focused or is minimized.

        Silently does nothing if the current desktop environment has no
        system tray at all (some minimal Linux setups) -- there's no
        good fallback for "native notification" that isn't itself a
        native notification, so this degrades to simply not showing one
        rather than trying to fake it some other way."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        if self._tray_icon is None:
            icon_path = resource_root() / "packaging" / "assets" / "icon.png"
            icon = QIcon(str(icon_path)) if icon_path.exists() else self.windowIcon()
            self._tray_icon = QSystemTrayIcon(icon, self)
            self._tray_icon.setToolTip(self.windowTitle() or "MarvelVerse Tracker")
            self._tray_icon.show()

        self._tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 8000)

    def update_library_summary(self, summary) -> None:
        """Update the status bar chips from a services.statistics_service.LibrarySummary.
        Takes a plain object (duck-typed) so this module never has to import
        the services layer."""
        self.status_projects_chip.setText(f"{summary.total_projects} Projects")
        self.status_watched_chip.setText(
            f"{summary.watched_count} Watched ({summary.completion_percent}%)"
        )

    def update_dashboard_stats(self, stats) -> None:
        """Refresh the Dashboard page from a
        services.statistics_service.DashboardStats. Takes a plain, duck-typed
        object so this module never has to import the services layer."""
        self.dashboard_view.set_stats(stats)

    def set_timeline_filter_options(self, options) -> None:
        """Populate the Timeline page's universe filter from a
        services.project_service.FilterOptions-shaped object (the same
        one the Library uses). Takes a plain, duck-typed object so this
        module never has to import the services layer."""
        self.timeline_view.set_filter_options(options)

    def set_timeline_groups(self, groups) -> None:
        """Refresh the Timeline page from a tuple of
        services.timeline_service.TimelineGroup-shaped objects. Takes
        plain, duck-typed objects so this module never has to import the
        services layer."""
        self.timeline_view.set_groups(groups)

    def set_achievements(self, statuses) -> None:
        """Refresh the Achievements page from a tuple of duck-typed
        services.achievement_service.AchievementStatus objects. Takes
        plain, duck-typed objects so this module never has to import the
        services layer."""
        self.achievements_view.set_achievements(statuses)

    def show_project_detail(self, detail) -> None:
        """Populate the Project Details page from a duck-typed
        ``services.project_service.ProjectDetail`` and switch to it.
        Deliberately doesn't change the sidebar's selection -- whichever
        page the project was activated from stays highlighted as "where
        you came from", and is recorded so the Back button returns there
        (see _detail_return_index)."""
        current_index = self.pages.currentIndex()
        if current_index != self._detail_page_index:
            self._detail_return_index = current_index
        self.project_detail_view.set_project(detail)
        self.pages.setCurrentIndex(self._detail_page_index)
        self.toolbar.set_page_title(detail.title)
        self.page_changed.emit("project_detail")
        self._animate_current_page()

    def show_person_detail(self, detail) -> None:
        """Populate the Actor/Director Details page from a duck-typed
        ``services.person_service.PersonDetail`` and switch to it.
        Person Details is only ever reached from Project Details' own
        cast/crew list, so its Back button always returns there directly
        (see _on_person_detail_back_requested) -- this doesn't need to
        touch _detail_return_index at all, unlike show_project_detail."""
        self.person_detail_view.set_person(detail)
        self.pages.setCurrentIndex(self._person_detail_page_index)
        self.toolbar.set_page_title(detail.name)
        self.page_changed.emit("person_detail")
        self._animate_current_page()

    def refresh_project_detail(self, detail) -> None:
        """Push updated data into the Project Details page without
        changing navigation -- used after a user-data edit is saved."""
        self.project_detail_view.set_project(detail)
        if self.pages.currentIndex() == self._detail_page_index:
            self.toolbar.set_page_title(detail.title)

    def set_project_episodes(self, episodes) -> None:
        self.project_detail_view.set_episodes(episodes)

    def set_tmdb_sync_status(self, message: str) -> None:
        """Push a TMDB sync summary/error message into the Settings page.
        Takes a plain string so this module never has to import the
        services layer (SyncResult.summary() is computed by the
        controller)."""
        self.settings_view.set_sync_status(message)

    def set_tmdb_sync_in_progress(self, in_progress: bool) -> None:
        self.settings_view.set_sync_in_progress(in_progress)

    def set_backups(self, backups) -> None:
        """Repopulate the Settings page's backup list from a tuple of
        duck-typed services.backup_service.BackupInfo objects. Takes
        plain, duck-typed objects so this module never has to import the
        services layer."""
        self.settings_view.set_backups(backups)

    def set_backup_status(self, message: str) -> None:
        self.settings_view.set_backup_status(message)

    def set_import_export_status(self, message: str) -> None:
        self.settings_view.set_import_export_status(message)

    def set_database_status(self, connected: bool) -> None:
        if connected:
            self.status_db_chip.setObjectName("statusChipOk")
            self.status_db_chip.setText("● Database Connected")
        else:
            self.status_db_chip.setObjectName("statusChipError")
            self.status_db_chip.setText("● Database Error")
        # Re-polish so the QSS objectName-based style actually refreshes.
        self.status_db_chip.style().unpolish(self.status_db_chip)
        self.status_db_chip.style().polish(self.status_db_chip)
