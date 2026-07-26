from __future__ import annotations

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

_TMDB_SIGNUP_URL = "https://www.themoviedb.org/signup"
_TMDB_API_SETTINGS_URL = "https://www.themoviedb.org/settings/api"


class TMDBOnboardingDialog(QDialog):
    """Shown once on first launch (or on any launch afterward, until
    either a key is saved or the user explicitly dismisses it -- see
    main.py) when no TMDB API key is configured yet. Explains what the
    key unlocks, walks through getting one, and lets the user paste it
    in directly, save it for later, or dismiss the prompt for good.

    This dialog only *collects* the key and reports back what the user
    chose -- it never touches AppConfig or triggers a sync itself; the
    caller (main.py) is responsible for actually saving it and kicking
    off whatever should happen next, same separation of concerns as
    every other dialog in this app.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to MarvelVerse Tracker")
        self.setMinimumWidth(480)
        self.setModal(True)

        self.entered_key: str | None = None
        self.dismissed_permanently = False

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        heading = QLabel("Connect your TMDB account")
        heading.setObjectName("pageHeading")
        layout.addWidget(heading)

        intro = QLabel(
            "MarvelVerse Tracker uses The Movie Database (TMDB) to pull in "
            "posters, synopses, cast & crew, trailers, and new releases as "
            "they're announced."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        warning = QLabel(
            "⚠ Without an API key, the app will still work with the "
            "catalog it ships with, but it won't be able to sync new "
            "releases, fetch trailers, pull poster art for anything not "
            "already in the library, or use \"Find on TMDB\" -- the app "
            "will not operate at full capacity until a key is added."
        )
        warning.setObjectName("emptyState")
        warning.setWordWrap(True)
        layout.addWidget(warning)

        steps_heading = QLabel("How to get a free API key (about 2 minutes):")
        steps_heading.setObjectName("sectionHeading")
        layout.addWidget(steps_heading)

        steps = QLabel(
            "1. Create a free TMDB account and verify your email\n"
            "2. Go to Settings → API on themoviedb.org and click Create\n"
            "3. Choose \"Developer\" when asked what type of key you need\n"
            "4. Fill out the short form (any app name/description is fine "
            "-- there's no review wait)\n"
            "5. Copy the \"API Key (v3 auth)\" value -- a 32-character "
            "string -- and paste it below"
        )
        steps.setWordWrap(True)
        layout.addWidget(steps)

        links_row = QHBoxLayout()
        self.open_signup_button = QPushButton("Open TMDB Sign Up")
        self.open_signup_button.setObjectName("secondaryButton")
        self.open_signup_button.clicked.connect(self._on_open_signup_clicked)
        links_row.addWidget(self.open_signup_button)

        self.open_api_settings_button = QPushButton("Open TMDB API Settings")
        self.open_api_settings_button.setObjectName("secondaryButton")
        self.open_api_settings_button.clicked.connect(self._on_open_api_settings_clicked)
        links_row.addWidget(self.open_api_settings_button)
        links_row.addStretch()
        layout.addLayout(links_row)

        self.key_input = QLineEdit()
        self.key_input.setObjectName("searchBox")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("Paste your TMDB API key here")
        layout.addWidget(self.key_input)

        self.dont_show_again_checkbox = QCheckBox("Don't ask me again (I'll add a key later in Settings if I want one)")
        layout.addWidget(self.dont_show_again_checkbox)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.skip_button = QPushButton("Skip For Now")
        self.skip_button.setObjectName("secondaryButton")
        self.skip_button.clicked.connect(self._on_skip_clicked)
        button_row.addWidget(self.skip_button)

        self.save_button = QPushButton("Save & Continue")
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.save_button)

        layout.addLayout(button_row)

    def _on_open_signup_clicked(self) -> None:
        QDesktopServices.openUrl(QUrl(_TMDB_SIGNUP_URL))

    def _on_open_api_settings_clicked(self) -> None:
        QDesktopServices.openUrl(QUrl(_TMDB_API_SETTINGS_URL))

    def _on_save_clicked(self) -> None:
        key = self.key_input.text().strip()
        if not key:
            # Nothing entered -- treat this the same as Skip rather than
            # silently closing with an empty "saved" key.
            self._on_skip_clicked()
            return
        self.entered_key = key
        self.dismissed_permanently = self.dont_show_again_checkbox.isChecked()
        self.accept()

    def _on_skip_clicked(self) -> None:
        self.entered_key = None
        self.dismissed_permanently = self.dont_show_again_checkbox.isChecked()
        self.reject()
