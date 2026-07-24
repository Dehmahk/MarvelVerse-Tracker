from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QSizePolicy, QToolBar, QWidget


class MainToolBar(QToolBar):
    """The application's top toolbar: sidebar collapse toggle, current page
    title, a global search box, and a refresh action. Purely presentational;
    it emits signals and lets the controller decide what to do."""

    refresh_requested = Signal()
    sidebar_toggle_requested = Signal()
    search_changed = Signal(str)
    surprise_me_requested = Signal()

    def __init__(self) -> None:
        super().__init__("Main Toolbar")
        self.setObjectName("mainToolbar")
        self.setMovable(False)
        self.setFloatable(False)

        self._collapse_button = QPushButton("☰")
        self._collapse_button.setObjectName("iconButton")
        self._collapse_button.setToolTip("Toggle sidebar")
        self._collapse_button.clicked.connect(self.sidebar_toggle_requested.emit)
        self.addWidget(self._collapse_button)

        self._brand_label = QLabel("  MARVELVERSE TRACKER")
        self._brand_label.setObjectName("toolbarTitle")
        self.addWidget(self._brand_label)

        self._page_label = QLabel("")
        self._page_label.setObjectName("toolbarPageLabel")
        self.addWidget(self._page_label)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.addWidget(spacer)

        self._search_box = QLineEdit()
        self._search_box.setObjectName("searchBox")
        self._search_box.setPlaceholderText("Search titles, cast & crew...")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.setMinimumWidth(320)
        self._search_box.setMaximumWidth(420)
        self._search_box.textChanged.connect(self.search_changed.emit)
        self.addWidget(self._search_box)

        self._surprise_me_button = QPushButton("🎲  Surprise Me")
        self._surprise_me_button.setObjectName("secondaryButton")
        self._surprise_me_button.setToolTip("Pick something random to watch")
        self._surprise_me_button.clicked.connect(self.surprise_me_requested.emit)
        self.addWidget(self._surprise_me_button)

        self._refresh_button = QPushButton("⟳  Refresh")
        self._refresh_button.setObjectName("secondaryButton")
        self._refresh_button.setToolTip("Refresh")
        self._refresh_button.clicked.connect(self.refresh_requested.emit)
        self.addWidget(self._refresh_button)

    def set_page_title(self, title: str) -> None:
        self._page_label.setText(f"  ·  {title.upper()}" if title else "")

    def search_text(self) -> str:
        return self._search_box.text()

    def clear_search(self) -> None:
        self._search_box.clear()
