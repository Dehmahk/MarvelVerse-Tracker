from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from controllers.application_controller import ApplicationController
from resource_paths import resource_root
from settings.config import AppConfig
from services.logging_service import configure_logging
from views.font_scaling import apply_font_scale
from views.widgets.tmdb_onboarding_dialog import TMDBOnboardingDialog

# Where to put splashscreen.png -- packaging/assets/ already holds the app
# icon, so this keeps every branding image asset in one place.
# packaging/MarvelVerseTracker.spec already bundles this whole folder for
# a packaged .exe; running from source, resource_root() just resolves to
# the project root directly.
SPLASH_IMAGE_PATH = resource_root() / "packaging" / "assets" / "splashscreen.png"


def _maybe_show_tmdb_onboarding(controller: ApplicationController) -> None:
    """Shown once the main window is up, if there's no TMDB API key
    configured yet (checked via resolved_tmdb_api_key(), so a
    TMDB_API_KEY environment variable also correctly suppresses this)
    and the user hasn't previously dismissed it for good. Collecting the
    key is the dialog's job; actually saving it, reflecting it in
    Settings, and kicking off a first sync are this function's."""
    config = controller.config
    if config.resolved_tmdb_api_key() or config.dismissed_api_key_prompt:
        return
    if controller.main_window is None:
        return

    dialog = TMDBOnboardingDialog(controller.main_window)
    dialog.exec()

    if dialog.dismissed_permanently:
        config.dismissed_api_key_prompt = True
        config.save()

    if dialog.entered_key:
        config.tmdb_api_key = dialog.entered_key
        config.save()
        controller.main_window.settings_view.api_key_input.setText(dialog.entered_key)
        controller.main_window.show_status_message("TMDB API key saved -- syncing now…")
        controller._run_tmdb_sync(manual=True)


def main() -> int:
    config = AppConfig.load()
    configure_logging(config.log_file)

    app = QApplication(sys.argv)
    app.setApplicationName(config.application_name)
    app.setApplicationDisplayName(config.application_name)
    app.setOrganizationName("MarvelVerseTracker")
    apply_font_scale(app, config.font_scale)

    # Entirely optional -- if splashscreen.png isn't there (e.g. a fresh
    # clone before it's been added), the app just starts normally with no
    # splash rather than failing to launch over a missing image.
    splash: QSplashScreen | None = None
    if SPLASH_IMAGE_PATH.exists():
        pixmap = QPixmap(str(SPLASH_IMAGE_PATH))
        if not pixmap.isNull():
            splash = QSplashScreen(pixmap)
            splash.showMessage(
                "Loading MarvelVerse Tracker…",
                Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                Qt.GlobalColor.white,
            )
            splash.show()
            # Database init/migrations inside controller.start() below are
            # synchronous and block the event loop -- without this, the
            # splash would never actually get painted before that work
            # runs, defeating the point of showing it first.
            app.processEvents()

    controller = ApplicationController(app, config)
    controller.start()

    if splash is not None and controller.main_window is not None:
        splash.finish(controller.main_window)

    _maybe_show_tmdb_onboarding(controller)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
