from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
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

# Prefer the .ico on Windows -- it embeds several resolutions (16x16 up
# through 256x256) so Windows can pick the right size for the taskbar,
# title bar, and Alt-Tab switcher without upscaling a single fixed-size
# image. Falls back to the .png (used elsewhere for the tray icon
# anyway) on platforms/setups where the .ico isn't present.
_ICON_ICO_PATH = resource_root() / "packaging" / "assets" / "icon.ico"
_ICON_PNG_PATH = resource_root() / "packaging" / "assets" / "icon.png"

# A unique-enough identifier so Windows treats this as its own distinct
# application rather than grouping/falling back to whatever generic
# icon it associates with the interpreter (or PyInstaller bootloader)
# that's actually running the process underneath.
_WINDOWS_APP_USER_MODEL_ID = "Dehmahk.MarvelVerseTracker"


def _set_windows_app_user_model_id() -> None:
    """Without this, Windows can show the correct icon in the title bar
    (that one comes straight from QApplication.setWindowIcon()) while
    still showing some other icon in the taskbar -- a well-documented
    quirk for Python/PyInstaller GUI apps specifically, since Windows
    identifies "which application is this really" for taskbar grouping
    and icon purposes via an "AppUserModelID", and without one
    explicitly set, it falls back to identifying the process by its
    underlying interpreter/bootloader rather than this app itself.
    Must be called before any window is shown -- ideally as close to
    the very start of the process as possible. A no-op (and safe to
    call) on any platform other than Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_WINDOWS_APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        # Best-effort -- an older/unusual Windows setup without this
        # shell32 function shouldn't prevent the app from starting at
        # all, it would just mean the taskbar icon quirk isn't fixed.
        pass


def _resolve_app_icon() -> QIcon | None:
    """The icon shown in the taskbar, title bar, and Alt-Tab switcher
    while the app is running -- entirely separate from the .exe file's
    own icon (that one's set at build time via
    packaging/MarvelVerseTracker.spec's icon= parameter, and only
    affects what Explorer shows for the file itself, not what Windows
    shows for the running window). Returns None if neither icon file
    exists, in which case Qt just falls back to its own default --
    same "missing asset degrades gracefully" approach as the splash
    screen above."""
    if _ICON_ICO_PATH.exists():
        return QIcon(str(_ICON_ICO_PATH))
    if _ICON_PNG_PATH.exists():
        return QIcon(str(_ICON_PNG_PATH))
    return None


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
    _set_windows_app_user_model_id()

    config = AppConfig.load()
    configure_logging(config.log_file)

    app = QApplication(sys.argv)
    app.setApplicationName(config.application_name)
    app.setApplicationDisplayName(config.application_name)
    app.setOrganizationName("MarvelVerseTracker")
    apply_font_scale(app, config.font_scale)

    app_icon = _resolve_app_icon()
    if app_icon is not None:
        app.setWindowIcon(app_icon)

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
