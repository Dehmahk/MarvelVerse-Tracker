from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from settings.config import AppConfig
from views.main_window import MainWindow

logger = logging.getLogger(__name__)


class ApplicationController:
    def __init__(self, app: QApplication, config: AppConfig) -> None:
        self.app = app
        self.config = config
        self.main_window: MainWindow | None = None

        # Library query state lives here, not in the view -- the view only
        # ever sees primitive values in and duck-typed results out. Seeded
        # from Settings > Library & Browsing's saved defaults rather than
        # hardcoded, so "Default View"/"Default Sort"/"Page Size"/"Show
        # upcoming" actually take effect at startup.
        from services.project_service import ProjectFilter, SortDirection, SortField

        self._library_filters = ProjectFilter(exclude_unreleased=not config.library_show_upcoming)
        try:
            self._library_sort_field = SortField(config.library_default_sort_field)
        except ValueError:
            self._library_sort_field = SortField.TITLE
        try:
            self._library_sort_direction = SortDirection(config.library_default_sort_direction)
        except ValueError:
            self._library_sort_direction = SortDirection.ASC
        self._library_page = 1
        self._library_page_size = max(1, config.library_default_page_size)

        # Timeline query state, mirroring the library state above -- same
        # "seed from Settings > Timeline's saved defaults" story.
        from services.timeline_service import TimelineSortMode

        self._timeline_universe_id: int | None = None
        try:
            self._timeline_sort_mode = TimelineSortMode(config.timeline_default_sort_mode)
        except ValueError:
            self._timeline_sort_mode = TimelineSortMode.PHASE
        self._timeline_excluded_sagas: frozenset[str] = frozenset(config.timeline_excluded_sagas)

        # Which collection is currently selected on the Collections page,
        # so an add/remove/reorder/rename action knows which detail to
        # re-push without the view needing to round-trip its own current
        # selection back to us.
        self._current_collection_id: int | None = None

        # Set the first time a "releasing soon" reminder is shown, so it
        # only ever surfaces once per session (the Dashboard can refresh
        # many times in one sitting -- e.g. after every rating change if
        # it's the visible page -- and re-announcing the same upcoming
        # release every time would be spammy, not helpful).
        self._release_reminder_shown = False
        self._native_release_notification_shown = False
        self._current_project_detail_type = None
        self._episode_details_sync_thread = None
        self._tmdb_sync_thread = None
        self._update_check_thread = None
        self._update_download_thread = None
        self._latest_update_info = None
        self._update_prompt_shown = False
        self._tmdb_search_thread = None
        self._tmdb_link_thread = None
        self._find_on_tmdb_project_id = None
        self._find_on_tmdb_project_type = None

        # Page keys ("library", "dashboard", "timeline", "achievements")
        # whose data is out of date and needs recomputing before it's next
        # shown. Populated by _mark_pages_stale() after any user action
        # that could move a count/rating/achievement -- deliberately
        # *not* refreshed immediately for pages the user isn't currently
        # looking at (see _refresh_stale_page()'s docstring for why).
        self._stale_pages: set[str] = set()

    def start(self) -> None:
        logger.info("Starting MarvelVerse Tracker")

        if not self._init_database():
            return

        self.app.aboutToQuit.connect(self._on_about_to_quit)

        self.main_window = MainWindow(self.config)
        self.main_window.refresh_requested.connect(self._on_refresh_requested)
        self.main_window.surprise_me_requested.connect(self._on_surprise_me_requested)
        self.main_window.check_for_updates_requested.connect(self._on_check_for_updates_requested)
        self.main_window.run_data_integrity_check_requested.connect(self._on_run_data_integrity_check_requested)
        self.main_window.find_on_tmdb_requested.connect(self._on_find_on_tmdb_requested)
        self.main_window.install_update_requested.connect(self._on_install_update_requested)
        self.main_window.search_changed.connect(self._on_search_changed)

        library = self.main_window.library_view
        library.filters_changed.connect(self._on_library_filters_changed)
        library.sort_changed.connect(self._on_library_sort_changed)
        library.page_changed.connect(self._on_library_page_changed)
        library.view_mode_changed.connect(self._on_library_view_mode_changed)
        library.clear_filters_requested.connect(self._on_library_clear_filters)

        self.main_window.project_activated.connect(self._on_project_activated)
        self.main_window.person_activated.connect(self._on_person_activated)
        self.main_window.episode_toggled.connect(self._on_episode_toggled)
        self.main_window.season_toggled.connect(self._on_season_toggled)
        self.main_window.sync_episode_details_requested.connect(self._on_sync_episode_details_requested)
        self.main_window.collection_activated.connect(self._on_collection_activated_from_dashboard)
        self.main_window.user_data_field_changed.connect(self._on_user_data_field_changed)
        self.main_window.log_watch_requested.connect(self._on_log_watch_requested)
        self.main_window.timeline_universe_changed.connect(self._on_timeline_universe_changed)
        self.main_window.timeline_sort_mode_changed.connect(self._on_timeline_sort_mode_changed)
        self.main_window.tmdb_api_key_changed.connect(self._on_tmdb_api_key_changed)
        self.main_window.tmdb_sync_requested.connect(self._on_tmdb_sync_requested)
        self.main_window.backup_requested.connect(self._on_backup_requested)
        self.main_window.restore_requested.connect(self._on_restore_requested)
        self.main_window.delete_backup_requested.connect(self._on_delete_backup_requested)
        self.main_window.export_requested.connect(self._on_export_requested)
        self.main_window.import_requested.connect(self._on_import_requested)
        self.main_window.compare_with_friend_requested.connect(self._on_compare_with_friend_requested)
        self.main_window.page_changed.connect(self._on_active_page_changed)
        self.main_window.preferences_changed.connect(self._on_preferences_changed)

        collections = self.main_window.collections_view
        collections.collection_selected.connect(self._on_collection_selected)
        collections.create_collection_requested.connect(self._on_create_collection_requested)
        collections.rename_collection_requested.connect(self._on_rename_collection_requested)
        collections.delete_collection_requested.connect(self._on_delete_collection_requested)
        collections.add_project_requested.connect(self._on_add_project_to_collection_requested)
        collections.remove_project_requested.connect(self._on_remove_project_from_collection_requested)
        collections.move_project_requested.connect(self._on_move_project_in_collection_requested)

        # Reflect the configured default sort in the combo itself -- the
        # query state it corresponds to was already seeded in __init__,
        # this just keeps the widget from misleadingly showing "Title
        # (A-Z)" while actually querying by something else.
        library.set_default_sort(self._library_sort_field.value, self._library_sort_direction.value)

        self.main_window.show()

        self._refresh_library_summary()
        self._load_library_filter_options()
        self._refresh_library_page()
        self._refresh_dashboard_stats()
        self._load_timeline_filter_options()
        self._load_timeline_saga_options()
        self._refresh_timeline()
        self._refresh_calendar()
        self._refresh_collections_list()
        self._refresh_achievements()
        self._refresh_backups()
        self._maybe_auto_sync_tmdb()
        self._maybe_run_scheduled_tmdb_sync()
        self._maybe_run_scheduled_backup()
        self._start_update_check(manual=False)

        logger.info("Main window displayed")

    # --- toolbar -------------------------------------------------------------

    def _on_refresh_requested(self) -> None:
        logger.info("Manual refresh requested from toolbar")
        self._refresh_library_summary()
        self._refresh_library_page()
        self._refresh_dashboard_stats()
        self._refresh_timeline()
        self._refresh_calendar()
        self._refresh_achievements()
        if self.main_window is not None:
            self._notify("Refreshed")

    def _on_surprise_me_requested(self) -> None:
        """Pick a random not-yet-watched, not-skipped RELEASED project and
        open its Project Details page directly -- available from every
        page via the toolbar, not just the Library."""
        if self.main_window is None:
            return

        from services.project_service import get_surprise_me_pick

        try:
            project_id = get_surprise_me_pick()
        except Exception:
            logger.exception("Failed to pick a surprise")
            self.main_window.show_status_message("Couldn't pick something -- check logs")
            return

        if project_id is None:
            self.main_window.show_status_message(
                "Nothing left to surprise you with -- looks like you're all caught up!"
            )
            return

        self._on_project_activated(project_id)

    # --- Updates -----------------------------------------------------------------

    def _start_update_check(self, *, manual: bool) -> None:
        """Kicks off a check of version.GITHUB_REPO's latest Release on
        a background thread (see controllers.update_check_worker) and
        returns immediately. `manual` distinguishes the automatic
        startup check (silent if there's nothing new -- no need to tell
        the user "you're already up to date" every single launch) from
        an explicit "Check for Updates" click (always reports back,
        even when there's nothing new)."""
        if self.main_window is None:
            return
        if self._update_check_thread is not None:
            if manual:
                self.main_window.show_status_message("Already checking for updates.")
            return

        from controllers.update_check_worker import UpdateCheckWorker
        from version import APP_VERSION, GITHUB_REPO

        if manual:
            self.main_window.settings_view.set_update_check_in_progress(True)

        worker = UpdateCheckWorker(APP_VERSION, GITHUB_REPO, self.app)
        worker.finished_checking.connect(lambda info: self._on_update_check_finished(info, manual))
        worker.finished.connect(self._on_update_check_thread_finished)
        self._update_check_thread = worker
        worker.start()

    def _on_update_check_thread_finished(self) -> None:
        self._update_check_thread = None
        if self.main_window is not None:
            self.main_window.settings_view.set_update_check_in_progress(False)

    def _on_update_check_finished(self, info, manual: bool) -> None:
        if self.main_window is None:
            return

        self._latest_update_info = info

        if info is None:
            if manual:
                self.main_window.settings_view.set_no_update_available()
            return

        self.main_window.settings_view.show_update_available(info)

        if manual:
            return

        # From here down is the automatic startup check's own behavior --
        # a manual "Check for Updates" click already got its answer via
        # the Settings panel just above, and doesn't need a popup on top
        # of an action the user just explicitly took.
        if self._update_prompt_shown:
            return
        self._update_prompt_shown = True

        if self.main_window.show_update_prompt(info.version, info.release_notes):
            self._on_install_update_requested()

    def _on_check_for_updates_requested(self) -> None:
        self._start_update_check(manual=True)

    def _on_run_data_integrity_check_requested(self) -> None:
        if self.main_window is None:
            return

        from services.data_integrity_service import check_data_integrity

        try:
            issues = check_data_integrity()
        except Exception:
            logger.exception("Data integrity check failed")
            self.main_window.show_status_message("Data integrity check failed -- check logs")
            return

        self.main_window.settings_view.show_data_integrity_results(issues)

    def _on_install_update_requested(self) -> None:
        """Downloads the update whose availability was already reported
        by the last check (see _latest_update_info) to the user's
        Downloads folder, with a versioned filename -- it's then up to
        them to close this app and run the new file themselves. This
        app deliberately does not try to replace its own running
        executable and relaunch automatically: that requires a fragile
        chain of self-replace tricks on Windows (this process exits,
        a detached script waits for the file lock to release, copies
        the new file over the old one, then relaunches it) that proved
        unreliable in practice -- manual, but actually reliable, beats
        automatic and broken.
        """
        if self.main_window is None or self._latest_update_info is None:
            return
        if self._update_download_thread is not None:
            return

        from controllers.update_download_worker import UpdateDownloadWorker
        from services.update_service import default_download_directory

        version = self._latest_update_info.version
        destination = default_download_directory() / f"MarvelVerseTracker-v{version}.exe"
        self.main_window.settings_view.set_update_install_in_progress("Downloading update…")

        worker = UpdateDownloadWorker(self._latest_update_info, destination, self.app)
        worker.succeeded.connect(self._on_update_download_succeeded)
        worker.failed.connect(self._on_update_download_failed)
        worker.finished.connect(self._on_update_download_thread_finished)
        self._update_download_thread = worker
        worker.start()

    def _on_update_download_thread_finished(self) -> None:
        self._update_download_thread = None

    def _on_update_download_succeeded(self, path) -> None:
        """The new .exe finished downloading to path -- tell the user
        where it landed and let them take it from here (close this app,
        run the new one) rather than trying to replace/relaunch this
        process automatically."""
        if self.main_window is None:
            return
        self.main_window.settings_view.set_update_downloaded(path)

    def _on_update_download_failed(self, message: str) -> None:
        if self.main_window is None:
            return
        logger.error("Update download failed: %s", message)
        self.main_window.settings_view.set_update_install_failed(
            "Couldn't download the update -- check logs."
        )

    # --- deferred ("stale page") refresh after a data-mutating action -------

    def _mark_pages_stale_and_refresh_visible(self) -> None:
        """Call after any action that edits ``UserProjectData`` (rating,
        watched, favorite, notes, wishlist, rewatch) -- the kind of change
        that could move the Library's counts, the Dashboard's stats, the
        Timeline's badges, or an achievement's progress.

        The status-bar summary is cheap (a handful of COUNT queries) so it
        still refreshes immediately. The other four are not: Timeline in
        particular rebuilds every marker widget on the page (100+ for a
        full catalog), and rebuilding it -- or the Library grid, or the
        Dashboard, or Achievements -- for a page the user isn't even
        looking at (edits only ever come from the Project Detail page,
        which has no sidebar row of its own) is exactly what was freezing
        the UI for a few seconds on every single rating edit. Instead,
        this only marks those four pages stale; each one is actually
        recomputed the next time the user navigates to it (see
        _on_active_page_changed()), and then only that one page pays the
        cost, once.
        """
        self._refresh_library_summary()
        self._stale_pages.update({"library", "dashboard", "timeline", "achievements"})
        self._refresh_stale_page(self._current_page_key())

    def _on_active_page_changed(self, page_key: str) -> None:
        self._refresh_stale_page(page_key)

    def _current_page_key(self) -> str | None:
        return self.main_window.current_page_key() if self.main_window is not None else None

    def _refresh_stale_page(self, page_key: str | None) -> None:
        if page_key is None or page_key not in self._stale_pages:
            return
        refresh_fn = {
            "library": self._refresh_library_page,
            "dashboard": self._refresh_dashboard_stats,
            "timeline": self._refresh_timeline,
            "calendar": self._refresh_calendar,
            "achievements": self._refresh_achievements,
        }.get(page_key)
        if refresh_fn is not None:
            refresh_fn()

    def _on_preferences_changed(self) -> None:
        """Settings > Library & Browsing/Timeline/Notifications/
        Personalization/Privacy were just saved (MainWindow already
        re-applied rating/date formatting locally before forwarding this).

        Default view mode and default sort only take effect the *next*
        time that page/session starts, deliberately: if the user has
        been actively sorting/filtering the Library this session, saving
        a new *default* sort in Settings shouldn't yank their current
        view out from under them -- Library has its own in-page combo/
        buttons for both of those, so there's a real "current session
        value" to protect.

        Page size doesn't have that concern -- there's no in-Library
        control for it at all, only this Settings field -- so unlike
        sort/view-mode, it's re-read and applied immediately below, and
        the current page resets to 1 in case the new page size means
        the page you were on no longer exists (e.g. going from 12/page
        on page 5 to 48/page, where there's now only 1-2 pages total).

        timeline_excluded_sagas is the other immediate-effect exception --
        it directly parametrizes the Timeline's Chronological computation.
        Combined with a forced refresh of whatever's currently visible,
        this also covers rating_scale/date_format/mask_ratings: those
        need already-rendered rows to actually re-render to show the new
        formatting, which a bare formatting.configure() call alone
        doesn't do."""
        self._timeline_excluded_sagas = frozenset(self.config.timeline_excluded_sagas)
        self._library_page_size = max(1, self.config.library_default_page_size)
        self._library_page = 1
        self._stale_pages.update({"library", "dashboard", "timeline", "achievements"})
        self._refresh_stale_page(self._current_page_key())

    def _on_search_changed(self, text: str) -> None:
        from dataclasses import replace

        self._library_filters = replace(self._library_filters, search_text=text)
        self._library_page = 1
        self._refresh_library_page()

    # --- library: filters / sort / paging / view mode -------------------------

    def _on_library_filters_changed(self, raw_filters: dict) -> None:
        from dataclasses import replace

        from models import ProjectStatus, ProjectType

        project_type = raw_filters.get("project_type")
        status = raw_filters.get("status")

        self._library_filters = replace(
            self._library_filters,
            universe_id=raw_filters.get("universe_id"),
            franchise_id=raw_filters.get("franchise_id"),
            genre_id=raw_filters.get("genre_id"),
            project_type=ProjectType(project_type) if project_type else None,
            status=ProjectStatus(status) if status else None,
            character_name=raw_filters.get("character_name"),
            watched=raw_filters.get("watched"),
            favorite=raw_filters.get("favorite"),
            wishlist=raw_filters.get("wishlist"),
            skipped=raw_filters.get("skipped"),
        )
        self._library_page = 1
        self._refresh_library_page()

    def _on_library_clear_filters(self) -> None:
        from dataclasses import replace

        # Preserve the global search box text; everything else resets.
        self._library_filters = replace(
            self._library_filters,
            universe_id=None,
            franchise_id=None,
            genre_id=None,
            project_type=None,
            status=None,
            watched=None,
            favorite=None,
            wishlist=None,
        )
        self._library_page = 1
        self._refresh_library_page()

    def _on_library_sort_changed(self, field: str, direction: str) -> None:
        from services.project_service import SortDirection, SortField

        self._library_sort_field = SortField(field)
        self._library_sort_direction = SortDirection(direction)
        self._library_page = 1
        self._refresh_library_page()

    def _on_library_page_changed(self, page: int) -> None:
        self._library_page = page
        self._refresh_library_page()

    def _on_library_view_mode_changed(self, _mode: str) -> None:
        # The view re-renders itself from the same data; a fresh query keeps
        # this handler simple and the result set trivially cheap on SQLite.
        self._refresh_library_page()

    def _load_library_filter_options(self) -> None:
        if self.main_window is None:
            return

        from services.project_service import get_filter_options

        try:
            options = get_filter_options()
        except Exception:
            logger.exception("Failed to load library filter options")
            return

        self.main_window.library_view.set_filter_options(options)

    def _refresh_library_page(self) -> None:
        if self.main_window is None:
            return

        from services.project_service import list_projects

        try:
            result = list_projects(
                filters=self._library_filters,
                sort_field=self._library_sort_field,
                sort_direction=self._library_sort_direction,
                page=self._library_page,
                page_size=self._library_page_size,
            )
        except Exception:
            logger.exception("Failed to load library page")
            self.main_window.show_status_message("Failed to load library -- check logs")
            return

        self.main_window.library_view.set_results(
            result, filters_active=self._library_filters.is_active()
        )
        self._stale_pages.discard("library")

    # --- project details --------------------------------------------------------

    def _on_project_activated(self, project_id: int) -> None:
        if self.main_window is None:
            return

        from services.project_service import get_project_detail

        try:
            detail = get_project_detail(project_id)
        except Exception:
            logger.exception("Failed to load project detail for id=%s", project_id)
            self.main_window.show_status_message("Failed to load project details -- check logs")
            return

        if detail is None:
            logger.warning("Project id=%s activated but no longer exists", project_id)
            self.main_window.show_status_message("That project could not be found.")
            return

        self.main_window.show_project_detail(detail)
        self._current_project_detail_type = detail.project_type
        self._refresh_project_episodes(project_id, detail.project_type)

    def _refresh_project_episodes(self, project_id: int, project_type) -> None:
        """Loads (generating first if needed) episode data for a
        TV-shaped project and pushes it into the Episodes panel; clears
        the panel for anything else. Split out from _on_project_activated
        so episode_toggled/season_toggled handlers can also call this
        same refresh after a change, without duplicating the TV-shaped
        check and error handling."""
        if self.main_window is None:
            return

        from models import ProjectType

        if project_type not in (ProjectType.TV_SERIES, ProjectType.ANIMATED_SERIES, ProjectType.TV_SPECIAL):
            self.main_window.set_project_episodes(())
            return

        from services.episode_service import ensure_episodes_exist, get_episodes

        try:
            ensure_episodes_exist(project_id)
            episodes = get_episodes(project_id)
        except Exception:
            logger.exception("Failed to load episodes for project id=%s", project_id)
            return

        self.main_window.set_project_episodes(episodes)

    def _on_episode_toggled(self, episode_id: int, watched: bool) -> None:
        if self.main_window is None:
            return

        from services.episode_service import set_episode_watched

        try:
            set_episode_watched(episode_id, watched)
        except Exception:
            logger.exception("Failed to toggle episode id=%s", episode_id)
            self.main_window.show_status_message("Failed to update episode -- check logs")
            return

        current_project_id = self.main_window.project_detail_view._project_id
        current_project_type = self._current_project_detail_type
        if current_project_id is not None:
            self._refresh_project_episodes(current_project_id, current_project_type)

    def _on_season_toggled(self, project_id: int, season_number: int, watched: bool) -> None:
        if self.main_window is None:
            return

        from services.episode_service import mark_season_watched

        try:
            mark_season_watched(project_id, season_number, watched)
        except Exception:
            logger.exception("Failed to toggle season %s for project id=%s", season_number, project_id)
            self.main_window.show_status_message("Failed to update season -- check logs")
            return

        self._refresh_project_episodes(project_id, self._current_project_detail_type)

    def _on_sync_episode_details_requested(self, project_id: int) -> None:
        if self.main_window is None:
            return
        if self._episode_details_sync_thread is not None:
            self.main_window.show_status_message("An episode sync is already in progress.")
            return

        api_key = self.config.resolved_tmdb_api_key()
        if not api_key:
            self.main_window.show_status_message("Add a TMDB API key in Settings first.")
            return

        from controllers.episode_details_sync_worker import EpisodeDetailsSyncWorker

        self.main_window.show_status_message("Syncing episode details from TMDB…")

        worker = EpisodeDetailsSyncWorker(project_id, api_key, self.app)
        worker.succeeded.connect(self._on_episode_details_sync_succeeded)
        worker.failed.connect(self._on_episode_details_sync_failed)
        worker.finished.connect(self._on_episode_details_sync_thread_finished)
        self._episode_details_sync_thread = worker
        worker.start()

    def _on_episode_details_sync_thread_finished(self) -> None:
        self._episode_details_sync_thread = None

    def _on_episode_details_sync_failed(self, message: str) -> None:
        if self.main_window is None:
            return
        logger.error("Episode details sync failed: %s", message)
        self.main_window.show_status_message(f"Couldn't sync episode details: {message}")

    def _on_episode_details_sync_succeeded(self, project_id: int) -> None:
        if self.main_window is None:
            return
        self.main_window.show_status_message("Episode details synced.")
        self._refresh_project_episodes(project_id, self._current_project_detail_type)

    def _on_person_activated(self, person_id: int) -> None:
        if self.main_window is None:
            return

        from services.person_service import get_person_detail

        try:
            detail = get_person_detail(person_id)
        except Exception:
            logger.exception("Failed to load person detail for id=%s", person_id)
            self.main_window.show_status_message("Failed to load actor/director details -- check logs")
            return

        if detail is None:
            logger.warning("Person id=%s activated but no longer exists", person_id)
            self.main_window.show_status_message("That person could not be found.")
            return

        self.main_window.show_person_detail(detail)

    def _on_collection_activated_from_dashboard(self, collection_id: int) -> None:
        """The Dashboard's Collections spotlight "View Collection" button
        was clicked -- switch to the Collections page and select that
        collection there, same end result as clicking it directly in the
        Collections list."""
        if self.main_window is None:
            return
        self.main_window.navigate_to_page("collections")
        self.main_window.collections_view.select_collection(collection_id)
        # select_collection() above should trigger collection_selected via
        # the list's currentRowChanged signal in the common case, but not
        # if this collection happened to already be the selected row (no
        # actual row change to emit) -- call explicitly too so the detail
        # panel is guaranteed correct either way. Harmless if it ends up
        # running twice.
        self._on_collection_selected(collection_id)

    def _notify(self, message: str) -> None:
        """Show a routine success confirmation ("Saved", "Logged", ...) --
        gated on Settings > Notifications' "status bar confirmations"
        toggle. Error messages should keep calling
        main_window.show_status_message(...) directly rather than this:
        those need to stay visible regardless of the preference, since
        silently swallowing a failure notice would be actively harmful."""
        if self.main_window is not None and self.config.notify_status_messages:
            self.main_window.show_status_message(message)

    def _on_user_data_field_changed(self, project_id: int, field: str, value) -> None:
        from services.project_service import update_user_project_data

        try:
            detail = update_user_project_data(project_id, **{field: value})
        except Exception:
            logger.exception("Failed to update %s for project id=%s", field, project_id)
            if self.main_window is not None:
                self.main_window.show_status_message("Failed to save change -- check logs")
            return

        if self.main_window is not None:
            self.main_window.refresh_project_detail(detail)
            self._notify("Saved")

        self._mark_pages_stale_and_refresh_visible()

    def _on_log_watch_requested(self, project_id: int, watched_with: str) -> None:
        from services.project_service import log_watch

        try:
            detail = log_watch(project_id, watched_with=watched_with or None)
        except Exception:
            logger.exception("Failed to log a watch for project id=%s", project_id)
            if self.main_window is not None:
                self.main_window.show_status_message("Failed to log watch -- check logs")
            return

        if self.main_window is not None:
            self.main_window.refresh_project_detail(detail)
            self._notify("Logged")

        self._mark_pages_stale_and_refresh_visible()

    # --- timeline -----------------------------------------------------------

    def _on_timeline_universe_changed(self, universe_id) -> None:
        self._timeline_universe_id = universe_id
        self._refresh_timeline()

    def _on_timeline_sort_mode_changed(self, sort_mode: str) -> None:
        from services.timeline_service import TimelineSortMode

        self._timeline_sort_mode = TimelineSortMode(sort_mode)
        self._refresh_timeline()

    def _load_timeline_filter_options(self) -> None:
        if self.main_window is None:
            return

        from services.project_service import get_filter_options

        try:
            options = get_filter_options()
        except Exception:
            logger.exception("Failed to load timeline filter options")
            return

        self.main_window.set_timeline_filter_options(options)

    def _load_timeline_saga_options(self) -> None:
        """Populate Settings > Timeline's saga-exclusion checklist. Lives
        alongside the timeline filter options rather than the settings
        panels themselves, since SettingsView never queries the database
        directly -- same rule as every other page."""
        if self.main_window is None:
            return

        from services.timeline_service import get_distinct_sagas

        try:
            sagas = get_distinct_sagas()
        except Exception:
            logger.exception("Failed to load saga options for Settings > Timeline")
            return

        self.main_window.settings_view.set_saga_options(sagas)

    def _refresh_timeline(self) -> None:
        if self.main_window is None:
            return

        from services.timeline_service import get_timeline

        try:
            groups = get_timeline(
                universe_id=self._timeline_universe_id,
                sort_mode=self._timeline_sort_mode,
                excluded_sagas=self._timeline_excluded_sagas,
            )
        except Exception:
            logger.exception("Failed to load timeline")
            self.main_window.show_status_message("Failed to load timeline -- check logs")
            return

        self.main_window.set_timeline_groups(groups)
        self._stale_pages.discard("timeline")

    def _refresh_calendar(self) -> None:
        if self.main_window is None:
            return

        from services.calendar_service import get_calendar_projects

        try:
            projects = get_calendar_projects()
        except Exception:
            logger.exception("Failed to load calendar")
            self.main_window.show_status_message("Failed to load calendar -- check logs")
            return

        self.main_window.calendar_view.set_projects(projects)
        self._stale_pages.discard("calendar")

    # --- collections -------------------------------------------------------------

    def _refresh_collections_list(self) -> None:
        if self.main_window is None:
            return

        from services.collection_service import list_collections

        try:
            summaries = list_collections()
        except Exception:
            logger.exception("Failed to load collections")
            self.main_window.show_status_message("Failed to load collections -- check logs")
            return

        self.main_window.collections_view.set_collections(summaries)
        self._update_dashboard_collection_spotlight(summaries)

    def _update_dashboard_collection_spotlight(self, summaries) -> None:
        """Push one collection (the first, alphabetically, with at least
        one project in it) into the Dashboard's spotlight -- called with
        the same summaries _refresh_collections_list() just computed,
        rather than re-querying list_collections() a second time. None
        (the spotlight section simply stays empty) if there are no
        collections yet, or none with any projects in them."""
        if self.main_window is None:
            return
        spotlight = next((summary for summary in summaries if summary.project_count > 0), None)
        self.main_window.dashboard_view.set_collection_spotlight(spotlight)

    def _refresh_collection_detail(self) -> None:
        """Re-push the currently-selected collection's detail (and its
        "Add Project" picker, which needs to exclude whatever's now a
        member) -- called after any action that could have changed
        either. A no-op if nothing's selected."""
        if self.main_window is None or self._current_collection_id is None:
            return

        from services.collection_service import get_collection_detail, get_pickable_projects

        try:
            detail = get_collection_detail(self._current_collection_id)
            pickable = get_pickable_projects(exclude_collection_id=self._current_collection_id)
        except Exception:
            logger.exception(
                "Failed to load detail for collection id=%s", self._current_collection_id
            )
            self.main_window.show_status_message("Failed to load collection -- check logs")
            return

        self.main_window.collections_view.set_collection_detail(detail)
        self.main_window.collections_view.set_pickable_projects(pickable)

    def _on_collection_selected(self, collection_id: int) -> None:
        self._current_collection_id = collection_id
        self._refresh_collection_detail()

    def _on_create_collection_requested(self, name: str, description: str) -> None:
        from services.collection_service import create_collection

        try:
            summary = create_collection(name, description)
        except ValueError as exc:
            self.main_window.show_status_message(str(exc))
            return
        except Exception:
            logger.exception("Failed to create collection %r", name)
            self.main_window.show_status_message("Failed to create collection -- check logs")
            return

        self._refresh_collections_list()
        self.main_window.collections_view.select_collection(summary.id)
        self._notify(f'Created "{summary.name}"')

    def _on_rename_collection_requested(self, collection_id: int, name: str, description: str) -> None:
        from services.collection_service import CollectionNotFoundError, rename_collection

        try:
            rename_collection(collection_id, name, description)
        except (ValueError, CollectionNotFoundError) as exc:
            self.main_window.show_status_message(str(exc))
            return
        except Exception:
            logger.exception("Failed to rename collection id=%s", collection_id)
            self.main_window.show_status_message("Failed to save changes -- check logs")
            return

        self._refresh_collections_list()
        self._refresh_collection_detail()
        self._notify("Saved")

    def _on_delete_collection_requested(self, collection_id: int) -> None:
        from services.collection_service import delete_collection

        try:
            delete_collection(collection_id)
        except Exception:
            logger.exception("Failed to delete collection id=%s", collection_id)
            self.main_window.show_status_message("Failed to delete collection -- check logs")
            return

        if self._current_collection_id == collection_id:
            self._current_collection_id = None
            self.main_window.collections_view.set_collection_detail(None)
        self._refresh_collections_list()
        self._notify("Collection deleted")

    def _on_add_project_to_collection_requested(self, collection_id: int, project_id: int) -> None:
        from services.collection_service import ProjectAlreadyInCollectionError, add_project_to_collection

        try:
            add_project_to_collection(collection_id, project_id)
        except (ProjectAlreadyInCollectionError, ValueError) as exc:
            self.main_window.show_status_message(str(exc))
            return
        except Exception:
            logger.exception(
                "Failed to add project id=%s to collection id=%s", project_id, collection_id
            )
            self.main_window.show_status_message("Failed to add project -- check logs")
            return

        self._refresh_collections_list()
        self._refresh_collection_detail()
        self._notify("Added to collection")

    def _on_remove_project_from_collection_requested(self, collection_id: int, project_id: int) -> None:
        from services.collection_service import remove_project_from_collection

        try:
            remove_project_from_collection(collection_id, project_id)
        except Exception:
            logger.exception(
                "Failed to remove project id=%s from collection id=%s", project_id, collection_id
            )
            self.main_window.show_status_message("Failed to remove project -- check logs")
            return

        self._refresh_collections_list()
        self._refresh_collection_detail()
        self._notify("Removed from collection")

    def _on_move_project_in_collection_requested(
        self, collection_id: int, project_id: int, direction: str
    ) -> None:
        from services.collection_service import move_project

        try:
            move_project(collection_id, project_id, direction)
        except ValueError:
            logger.exception(
                "Invalid move direction for project id=%s in collection id=%s", project_id, collection_id
            )
            return
        except Exception:
            logger.exception(
                "Failed to reorder project id=%s in collection id=%s", project_id, collection_id
            )
            self.main_window.show_status_message("Failed to reorder -- check logs")
            return

        self._refresh_collection_detail()

    def _refresh_library_summary(self) -> None:
        """Pull the latest library counts and push them into the shell's
        status bar. The window never queries the database itself."""
        if self.main_window is None:
            return

        from services.statistics_service import get_library_summary

        try:
            summary = get_library_summary()
        except Exception:
            logger.exception("Failed to load library summary")
            self.main_window.set_database_status(connected=False)
            return

        self.main_window.set_database_status(connected=True)
        self.main_window.update_library_summary(summary)

    def _refresh_dashboard_stats(self) -> None:
        """Pull the latest dashboard statistics and push them into the
        Dashboard page. Mirrors _refresh_library_summary's pattern; failures
        are logged and swallowed so a dashboard hiccup never blocks the rest
        of the refresh (the library/status-bar refreshes already surface
        their own error state)."""
        if self.main_window is None:
            return

        from services.statistics_service import get_dashboard_stats

        try:
            stats = get_dashboard_stats()
        except Exception:
            logger.exception("Failed to load dashboard stats")
            return

        self.main_window.update_dashboard_stats(stats)
        self._stale_pages.discard("dashboard")
        self._maybe_show_release_reminder(stats)

        from services.fun_facts_service import get_fact_of_the_day

        self.main_window.dashboard_view.set_fact_of_the_day(get_fact_of_the_day().text)

    def _maybe_show_release_reminder(self, stats) -> None:
        """Once per session, if the soonest "Coming Soon" release is
        within a week, surface it as a status message -- a lightweight
        stand-in for a real notification/reminder system, which would
        need a background scheduler this app doesn't have. Uses the same
        upcoming_releases list the Dashboard's "Coming Soon" strip
        already shows (soonest first), so there's no extra query."""
        if self._release_reminder_shown or not stats.upcoming_releases:
            return

        soonest = stats.upcoming_releases[0]
        if soonest.release_date is None:
            return

        from datetime import date

        days_until = (soonest.release_date - date.today()).days
        if not (0 <= days_until <= 7):
            return

        self._release_reminder_shown = True
        if days_until == 0:
            when = "today"
        elif days_until == 1:
            when = "tomorrow"
        else:
            when = f"in {days_until} days"
        self._notify(f"🎬 {soonest.title} releases {when}!")

        self._maybe_show_native_release_day_notification(stats)

    def _maybe_show_native_release_day_notification(self, stats) -> None:
        """A real OS desktop notification (separate from the in-app
        status message above), specifically for anything releasing
        *today* -- once per session, and only if the user hasn't turned
        it off in Settings > Notifications."""
        if self._native_release_notification_shown or self.main_window is None:
            return
        if not self.config.notify_release_day_native:
            return

        from datetime import date

        todays_releases = [r for r in stats.upcoming_releases if r.release_date == date.today()]
        if not todays_releases:
            return

        self._native_release_notification_shown = True
        if len(todays_releases) == 1:
            message = f'"{todays_releases[0].title}" is out today!'
        else:
            titles = ", ".join(r.title for r in todays_releases[:3])
            message = f"Out today: {titles}"
        self.main_window.show_native_notification("New Marvel Release", message)

    def _refresh_achievements(self) -> None:
        """Recompute achievement progress/unlocks and push the result into
        the Achievements page. Mirrors _refresh_dashboard_stats()'s
        pattern; failures are logged and swallowed so an achievements
        hiccup never blocks the rest of a refresh.

        Also surfaces a status-bar message for any achievement that
        unlocked as a direct result of whatever action triggered this
        refresh (a watch, a rating, a completed universe via TMDB sync,
        ...) -- but only the call that actually pushed it over the
        threshold ever reports it, per sync_achievements()'s contract, so
        a routine refresh with nothing new never spams the status bar."""
        if self.main_window is None:
            return

        from services.achievement_service import sync_achievements

        try:
            statuses, newly_unlocked = sync_achievements()
        except Exception:
            logger.exception("Failed to refresh achievements")
            return

        self.main_window.set_achievements(statuses)
        self._stale_pages.discard("achievements")

        self._update_dashboard_closest_achievement(statuses)

        if newly_unlocked:
            if self.config.achievement_sound_enabled:
                self.app.beep()
            if self.config.notify_achievement_unlocks:
                names = ", ".join(newly_unlocked)
                self.main_window.show_status_message(f"🏆 Achievement unlocked: {names}")

    def _update_dashboard_closest_achievement(self, statuses) -> None:
        """Push the locked achievement with the highest percent_complete
        into the Dashboard's hero row -- called with the same statuses
        _refresh_achievements() just computed, rather than re-running
        sync_achievements() a second time for the same data. None (shown
        as a placeholder card) if every achievement is already unlocked."""
        if self.main_window is None:
            return
        locked = [status for status in statuses if not status.is_unlocked]
        closest = max(locked, key=lambda status: status.percent_complete, default=None)
        self.main_window.dashboard_view.set_closest_achievement(closest)

    # --- TMDB (Milestone 8, part 2) -------------------------------------------

    def _on_tmdb_api_key_changed(self, key: str) -> None:
        # SettingsView already wrote the key to AppConfig and called
        # config.save() itself -- it holds the same AppConfig instance
        # this controller does, so self.config is already up to date here.
        # This handler just acknowledges the save in the status bar.
        if self.main_window is not None:
            self.main_window.show_status_message(
                "TMDB API key saved." if key else "TMDB API key cleared."
            )

    def _on_tmdb_sync_requested(self) -> None:
        self._run_tmdb_sync(manual=True)

    def _maybe_auto_sync_tmdb(self) -> None:
        """Run a one-time automatic TMDB sync on first launch, per the
        confirmed decision in README.md. Only runs once ever, gated by
        AppConfig.tmdb_auto_sync_attempted -- if no key is configured yet,
        this is skipped *without* setting that flag, so the app still gets
        one free automatic sync the first time a key does get configured,
        rather than only ever auto-syncing on literally the first launch."""
        if self.config.tmdb_auto_sync_attempted:
            return
        if not self.config.resolved_tmdb_api_key():
            return

        logger.info("Attempting one-time automatic TMDB sync")
        try:
            self._run_tmdb_sync(manual=False)
        finally:
            # Set regardless of outcome -- a bad/expired key should never
            # retry forever on every single launch.
            self.config.tmdb_auto_sync_attempted = True
            self.config.save()

    def _maybe_run_scheduled_tmdb_sync(self) -> None:
        """Re-sync from TMDB automatically if Settings > TMDB Integration's
        "Auto-Sync" interval is set (non-zero) and at least that many days
        have passed since tmdb_last_synced_at. Runs after
        _maybe_auto_sync_tmdb() in start() -- the two are independent
        (this one keys off tmdb_last_synced_at, that one off
        tmdb_auto_sync_attempted), so a fresh install still gets exactly
        one free sync even with the interval left at "Never"."""
        if self.config.tmdb_auto_sync_interval_days <= 0:
            return
        if not self.config.resolved_tmdb_api_key():
            return

        from datetime import datetime

        if self.config.tmdb_last_synced_at:
            try:
                last_synced = datetime.fromisoformat(self.config.tmdb_last_synced_at)
            except ValueError:
                last_synced = None
        else:
            last_synced = None

        if last_synced is not None:
            days_since = (datetime.now() - last_synced).total_seconds() / 86400
            if days_since < self.config.tmdb_auto_sync_interval_days:
                return

        logger.info("Running scheduled TMDB auto-sync (interval elapsed)")
        self._run_tmdb_sync(manual=False)

    def _run_tmdb_sync(self, *, manual: bool) -> None:
        """Kicks off a TMDB sync on a background thread (see
        controllers.tmdb_sync_worker.TMDBSyncWorker) and returns
        immediately -- the rest of the app stays fully responsive while
        it runs. set_tmdb_sync_in_progress() disables the Sync button and
        shows a busy message for the duration; _on_tmdb_sync_succeeded/
        _on_tmdb_sync_failed (connected below) pick up where the old
        synchronous version left off once the worker thread reports back.
        """
        if self.main_window is None:
            return

        if self._tmdb_sync_thread is not None:
            # A sync (manual or scheduled) is already running -- only
            # bother the user about it if *they* just asked for one;
            # a background-triggered attempt finding one already in
            # flight is expected and fine to just skip silently.
            if manual:
                self.main_window.show_status_message("A TMDB sync is already in progress.")
            return

        api_key = self.config.resolved_tmdb_api_key()
        if not api_key:
            self.main_window.set_tmdb_sync_status("No TMDB API key configured.")
            if manual:
                self.main_window.show_status_message("Add a TMDB API key first.")
            return

        from controllers.tmdb_sync_worker import TMDBSyncWorker

        self.main_window.set_tmdb_sync_in_progress(True)

        worker = TMDBSyncWorker(api_key, self.app)
        worker.succeeded.connect(lambda result: self._on_tmdb_sync_succeeded(result, manual))
        worker.failed.connect(lambda message: self._on_tmdb_sync_failed(message, manual))
        worker.finished.connect(self._on_tmdb_sync_thread_finished)
        self._tmdb_sync_thread = worker
        worker.start()

    def _on_about_to_quit(self) -> None:
        """Waits for any in-flight background TMDB sync to actually
        finish (rather than just abandoning it mid-request/mid-write)
        before disposing the database engine -- terminating a thread
        that's partway through a database write is exactly the kind of
        thing that could corrupt data on the way out. 10 seconds is
        generous for any single in-flight HTTP request/write to wrap up;
        if it's still not done by then, something's actually stuck, and
        waiting forever would just hang the app on quit instead.

        The update-check/download threads don't touch the database, but
        get the same treatment for the same underlying reason: a QThread
        object shouldn't outlive the QApplication that owns it."""
        for thread in (self._tmdb_sync_thread, self._update_check_thread, self._update_download_thread):
            if thread is not None:
                thread.wait(10_000)

        from database import dispose_engine

        dispose_engine()

    def _on_tmdb_sync_thread_finished(self) -> None:
        """Connected to QThread's own built-in `finished` signal (fires
        after `run()` returns, regardless of success/failure) -- clears
        our reference so a new sync can start, and re-enables the Sync
        button. Runs after _on_tmdb_sync_succeeded/_failed, which have
        already updated the status text."""
        self._tmdb_sync_thread = None
        if self.main_window is not None:
            self.main_window.set_tmdb_sync_in_progress(False)

    def _on_tmdb_sync_succeeded(self, result, manual: bool) -> None:
        if self.main_window is None:
            return

        self.main_window.set_tmdb_sync_status(result.summary())
        if manual:
            self.main_window.show_status_message(f"TMDB sync complete: {result.summary()}")

        from datetime import datetime

        self.config.tmdb_last_synced_at = datetime.now().isoformat()
        self.config.save()

        self._refresh_library_summary()
        self._refresh_library_page()
        self._refresh_dashboard_stats()
        self._refresh_timeline()
        self._refresh_achievements()

    def _on_tmdb_sync_failed(self, message: str, manual: bool) -> None:
        if self.main_window is None:
            return
        logger.error("TMDB sync failed: %s", message)
        self.main_window.set_tmdb_sync_status(f"Sync failed: {message}")
        if manual:
            self.main_window.show_status_message("TMDB sync failed -- check logs")

    # --- Find on TMDB (manual search + link, for projects a full sync -----------
    # would never discover -- see search_tmdb()'s own docstring) ----------------

    def _on_find_on_tmdb_requested(self, project_id: int) -> None:
        if self.main_window is None:
            return
        if self._tmdb_search_thread is not None or self._tmdb_link_thread is not None:
            self.main_window.show_status_message("A TMDB lookup is already in progress.")
            return

        api_key = self.config.resolved_tmdb_api_key()
        if not api_key:
            self.main_window.show_status_message("Add a TMDB API key in Settings first.")
            return

        from services.project_service import get_project_detail

        detail = get_project_detail(project_id)
        if detail is None:
            return

        from controllers.tmdb_search_worker import TMDBSearchWorker

        self._find_on_tmdb_project_id = project_id
        self._find_on_tmdb_project_type = detail.project_type
        self.main_window.show_status_message(f'Searching TMDB for "{detail.title}"…')

        worker = TMDBSearchWorker(api_key, detail.title, detail.project_type, self.app)
        worker.succeeded.connect(lambda results: self._on_tmdb_search_succeeded(results, detail.title))
        worker.failed.connect(self._on_tmdb_search_failed)
        worker.finished.connect(self._on_tmdb_search_thread_finished)
        self._tmdb_search_thread = worker
        worker.start()

    def _on_tmdb_search_thread_finished(self) -> None:
        self._tmdb_search_thread = None

    def _on_tmdb_search_failed(self, message: str) -> None:
        if self.main_window is None:
            return
        logger.error("TMDB search failed: %s", message)
        self.main_window.show_status_message(f"TMDB search failed: {message}")

    def _on_tmdb_search_succeeded(self, results, title: str) -> None:
        if self.main_window is None:
            return

        from views.widgets.tmdb_link_dialog import TMDBLinkDialog

        dialog = TMDBLinkDialog(results, title, self.main_window)
        if dialog.exec() != TMDBLinkDialog.DialogCode.Accepted or dialog.selected_result is None:
            return

        project_id = self._find_on_tmdb_project_id
        project_type = self._find_on_tmdb_project_type
        if project_id is None or project_type is None:
            return

        api_key = self.config.resolved_tmdb_api_key()
        if not api_key:
            self.main_window.show_status_message("Add a TMDB API key in Settings first.")
            return

        from controllers.tmdb_link_worker import TMDBLinkWorker

        self.main_window.show_status_message(f'Linking to "{dialog.selected_result.title}"…')

        worker = TMDBLinkWorker(project_id, dialog.selected_result.tmdb_id, project_type, api_key, self.app)
        worker.succeeded.connect(self._on_tmdb_link_succeeded)
        worker.failed.connect(self._on_tmdb_link_failed)
        worker.finished.connect(self._on_tmdb_link_thread_finished)
        self._tmdb_link_thread = worker
        worker.start()

    def _on_tmdb_link_thread_finished(self) -> None:
        self._tmdb_link_thread = None

    def _on_tmdb_link_failed(self, message: str) -> None:
        if self.main_window is None:
            return
        logger.error("TMDB link failed: %s", message)
        self.main_window.show_status_message(f"Couldn't link to TMDB: {message}")

    def _on_tmdb_link_succeeded(self, project_id: int) -> None:
        if self.main_window is None:
            return
        self.main_window.show_status_message("Linked to TMDB.")

        # Refresh whatever's currently showing this project, plus the
        # library/dashboard/timeline, since new poster art/genres/cast
        # can affect all of them -- same "mark stale, refresh what's
        # visible" pattern every other mutating action in this app uses.
        if self.main_window.current_page_key() == "project_detail":
            self._on_project_activated(project_id)
        self._stale_pages.update({"library", "dashboard", "timeline", "calendar"})
        self._refresh_stale_page(self._current_page_key())

    # --- Backups (Milestone 10) -----------------------------------------------

    def _refresh_backups(self) -> None:
        if self.main_window is None:
            return

        from services.backup_service import list_backups

        try:
            backups = list_backups(self.config)
        except Exception:
            logger.exception("Failed to list backups")
            return

        self.main_window.set_backups(backups)

    def _maybe_run_scheduled_backup(self) -> None:
        """Create an automatic backup at startup if Settings > Backups'
        "Automatically create backups" toggle is on and enough time has
        passed since the last one -- see
        services.backup_service.maybe_run_scheduled_backup() for the
        actual due-check/retention-pruning logic this just calls into.
        Refreshes the backups list afterward if one was actually created,
        so a freshly-opened Settings page shows it without needing a
        manual refresh."""
        from services.backup_service import maybe_run_scheduled_backup

        try:
            backup = maybe_run_scheduled_backup(self.config)
        except Exception:
            logger.exception("Scheduled auto-backup failed")
            return

        if backup is not None:
            self.config.save()
            logger.info("Scheduled auto-backup created at %s", backup.path)
            self._refresh_backups()

    def _on_backup_requested(self) -> None:
        if self.main_window is None:
            return

        from services.backup_service import create_backup

        try:
            backup = create_backup(self.config)
        except Exception:
            logger.exception("Failed to create backup")
            self.main_window.set_backup_status("Backup failed -- check logs.")
            self.main_window.show_status_message("Backup failed -- check logs")
            return

        self.main_window.set_backup_status(f"Backup created: {backup.filename}")
        self._notify("Backup created")
        self._refresh_backups()

    def _on_restore_requested(self, path: str) -> None:
        if self.main_window is None:
            return

        from pathlib import Path

        from services.backup_service import restore_backup

        try:
            restore_backup(self.config, Path(path))
        except Exception:
            logger.exception("Failed to restore backup %s", path)
            self.main_window.set_backup_status("Restore failed -- check logs.")
            self.main_window.show_status_message("Restore failed -- check logs")
            return

        self.main_window.set_backup_status("Backup restored.")
        self._notify("Backup restored")

        # The database underneath the app just changed out from under
        # every page at once -- refresh everything, the same full set of
        # pages a fresh start() populates, not just the ones a single
        # user action would normally touch.
        self._refresh_library_summary()
        self._load_library_filter_options()
        self._refresh_library_page()
        self._refresh_dashboard_stats()
        self._load_timeline_filter_options()
        self._refresh_timeline()
        self._refresh_achievements()
        self._refresh_backups()

    def _on_delete_backup_requested(self, path: str) -> None:
        if self.main_window is None:
            return

        from pathlib import Path

        from services.backup_service import delete_backup

        try:
            delete_backup(Path(path))
        except Exception:
            logger.exception("Failed to delete backup %s", path)
            self.main_window.set_backup_status("Couldn't delete that backup -- check logs.")
            return

        self.main_window.set_backup_status("Backup deleted.")
        self._refresh_backups()

    # --- Import / export (Milestone 10) ---------------------------------------

    def _on_export_requested(self, path: str) -> None:
        if self.main_window is None:
            return

        from pathlib import Path

        from services.data_export_service import export_user_data

        try:
            summary = export_user_data(Path(path))
        except Exception:
            logger.exception("Failed to export user data to %s", path)
            self.main_window.set_import_export_status("Export failed -- check logs.")
            self.main_window.show_status_message("Export failed -- check logs")
            return

        self.main_window.set_import_export_status(
            f"Exported {summary.project_count} project(s) to {Path(path).name}"
        )
        self._notify("Export complete")

    def _on_import_requested(self, path: str) -> None:
        if self.main_window is None:
            return

        from pathlib import Path

        from services.data_export_service import import_user_data

        try:
            summary = import_user_data(Path(path))
        except ValueError as exc:
            self.main_window.set_import_export_status(str(exc))
            self.main_window.show_status_message("Import failed -- check logs")
            return
        except Exception:
            logger.exception("Failed to import user data from %s", path)
            self.main_window.set_import_export_status("Import failed -- check logs.")
            self.main_window.show_status_message("Import failed -- check logs")
            return

        self.main_window.set_import_export_status(summary.summary())

    def _on_compare_with_friend_requested(self, path: str) -> None:
        if self.main_window is None:
            return

        from pathlib import Path

        from services.comparison_service import ComparisonFileError, compare_with_friend_export

        try:
            result = compare_with_friend_export(Path(path))
        except ComparisonFileError as exc:
            self.main_window.set_import_export_status(str(exc))
            return
        except Exception:
            logger.exception("Failed to compare with friend export at %s", path)
            self.main_window.set_import_export_status("Comparison failed -- check logs.")
            return

        self.main_window.settings_view.show_comparison_results(result)
        self._notify("Import complete")

        # Imported data can touch watched/rating/rewatch/achievement state
        # for any number of projects at once -- refresh every page that
        # could be affected, same as a successful TMDB sync does.
        self._refresh_library_summary()
        self._refresh_library_page()
        self._refresh_dashboard_stats()
        self._refresh_timeline()
        self._refresh_achievements()

    def _init_database(self) -> bool:
        """Initialize the SQLite database: run migrations and seed
        canonical reference data. Returns False (and shows an error dialog)
        if the database could not be brought up, so start() can bail out
        before ever creating a window backed by a broken database."""
        from database import init_database

        try:
            init_database(self.config.database_file, copy_bundled_catalog=True)
        except Exception:
            logger.exception("Failed to initialize the database")
            QMessageBox.critical(
                None,
                "Database Error",
                "MarvelVerse Tracker could not initialize its database and "
                "cannot continue. Check logs/application.log for details.",
            )
            return False

        logger.info("Database ready at %s", self.config.database_file)
        return True
