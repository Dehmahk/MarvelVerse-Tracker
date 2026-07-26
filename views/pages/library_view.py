from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from views.widgets.flow_layout import FlowLayout
from views.widgets.project_card import ProjectCard
from views.widgets.project_row import ProjectRow

VIEW_MODES = ("grid", "poster", "list", "compact")
_VIEW_MODE_ICONS = {"grid": "▦", "poster": "▭", "list": "☰", "compact": "≣"}
_VIEW_MODE_TOOLTIPS = {
    "grid": "Grid view",
    "poster": "Poster view",
    "list": "List view",
    "compact": "Compact view",
}

# (display label, sort_field value, sort_direction value) — matches
# services.project_service.SortField / SortDirection string values, but this
# module never imports that package; the controller does the translation.
# Public so Settings > Library & Browsing can offer the exact same list as
# a "default sort" choice, without duplicating it.
SORT_PRESETS = [
    ("Title (A–Z)", "title", "asc"),
    ("Title (Z–A)", "title", "desc"),
    ("Release Date (Newest)", "release_date", "desc"),
    ("Release Date (Oldest)", "release_date", "asc"),
    ("Rating (Highest)", "rating", "desc"),
    ("Rating (Lowest)", "rating", "asc"),
    ("Chronological Order", "chronological_order", "asc"),
    ("Recently Added", "recently_added", "desc"),
]

_TYPE_OPTIONS = [
    ("All Types", None),
    ("Movie", "movie"),
    ("TV Series", "tv_series"),
    ("TV Special", "tv_special"),
    ("Short", "short"),
    ("Documentary", "documentary"),
    ("Animated Series", "animated_series"),
]

_STATUS_OPTIONS = [
    ("All Statuses", None),
    ("Released", "released"),
    ("Upcoming", "upcoming"),
    ("Announced", "announced"),
    ("In Production", "in_production"),
    ("Cancelled", "cancelled"),
]

# Mirrors services.project_service.CHARACTER_FILTER_OPTIONS exactly --
# duplicated here rather than imported, same as _TYPE_OPTIONS/
# _STATUS_OPTIONS already duplicate ProjectType/ProjectStatus's values,
# since views in this app never import the services layer directly.
_CHARACTER_OPTIONS = (
    "Iron Man",
    "Captain America",
    "Thor",
    "Hulk",
    "Black Widow",
    "Hawkeye",
    "Nick Fury",
    "Loki",
    "Scarlet Witch",
    "Vision",
    "Ant-Man",
    "Wasp",
    "Doctor Strange",
    "Black Panther",
    "Captain Marvel",
    "Star-Lord",
    "Gamora",
    "Rocket",
    "Groot",
    "Drax",
    "Spider-Man",
    "Venom",
    "Morbius",
    "Wolverine",
    "Deadpool",
    "Professor X",
    "Magneto",
    "Mystique",
    "Cyclops",
    "Storm",
    "Jean Grey",
    "Ghost Rider",
    "Blade",
    "Daredevil",
    "The Punisher",
    "Jessica Jones",
    "Luke Cage",
    "Iron Fist",
    "Elektra",
    "Nova",
    "She-Hulk",
    "Ms. Marvel",
    "Moon Knight",
    "Shang-Chi",
    "Eternals",
)


class LibraryView(QWidget):
    """Browse, search, filter, sort, and page through the project library.

    This view never touches the database or services layer directly — it
    only knows primitive filter/sort values and duck-typed result objects
    handed to it by the controller, per the shell's architecture rule.
    Global text search lives in the toolbar; this view owns everything
    else (dropdown filters, sort, view mode, pagination).
    """

    filters_changed = Signal(dict)
    sort_changed = Signal(str, str)
    page_changed = Signal(int)
    view_mode_changed = Signal(str)
    clear_filters_requested = Signal()
    project_activated = Signal(int)

    def __init__(self, default_view_mode: str = "grid", poster_size_scale: float = 1.0) -> None:
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._view_mode = default_view_mode if default_view_mode in VIEW_MODES else "grid"
        self._poster_size_scale = poster_size_scale
        self._suspend_signals = False
        self._all_franchises: list[tuple[int, str, int]] = []
        self._current_page = 1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 20)
        layout.setSpacing(16)

        heading = QLabel("Library")
        heading.setObjectName("pageHeading")
        subtitle = QLabel("Browse your complete Marvel collection.")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(heading)
        layout.addWidget(subtitle)

        layout.addLayout(self._build_filter_bar())
        layout.addLayout(self._build_toolbar_row())

        self.content_stack = QScrollArea()
        self.content_stack.setObjectName("libraryScrollArea")
        self.content_stack.setWidgetResizable(True)
        self.content_stack.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self.content_stack, 1)

        self.empty_state = QLabel("")
        self.empty_state.setObjectName("emptyState")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.hide()
        layout.addWidget(self.empty_state)

        layout.addLayout(self._build_pagination_row())

        self._set_grid_container()

    # --- construction helpers ------------------------------------------------

    def _build_filter_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        self.universe_combo = QComboBox()
        self.universe_combo.setObjectName("filterCombo")
        self.franchise_combo = QComboBox()
        self.franchise_combo.setObjectName("filterCombo")
        self.genre_combo = QComboBox()
        self.genre_combo.setObjectName("filterCombo")

        self.type_combo = QComboBox()
        self.type_combo.setObjectName("filterCombo")
        for label, value in _TYPE_OPTIONS:
            self.type_combo.addItem(label, value)

        self.status_combo = QComboBox()
        self.status_combo.setObjectName("filterCombo")
        for label, value in _STATUS_OPTIONS:
            self.status_combo.addItem(label, value)

        self.character_combo = QComboBox()
        self.character_combo.setObjectName("filterCombo")
        self.character_combo.addItem("All Characters", None)
        for name in _CHARACTER_OPTIONS:
            self.character_combo.addItem(name, name)

        self.universe_combo.addItem("All Universes", None)
        self.franchise_combo.addItem("All Franchises", None)
        self.genre_combo.addItem("All Genres", None)

        self.watched_toggle = QPushButton("Watched")
        self.favorite_toggle = QPushButton("Favorites")
        self.wishlist_toggle = QPushButton("Wishlist")
        self.skipped_toggle = QPushButton("Skipped")
        for button in (
            self.watched_toggle,
            self.favorite_toggle,
            self.wishlist_toggle,
            self.skipped_toggle,
        ):
            button.setObjectName("filterToggle")
            button.setCheckable(True)

        self.clear_filters_button = QPushButton("Clear")
        self.clear_filters_button.setObjectName("secondaryButton")
        self.clear_filters_button.clicked.connect(self._on_clear_filters)

        for widget in (
            self.universe_combo,
            self.franchise_combo,
            self.genre_combo,
            self.type_combo,
            self.status_combo,
            self.character_combo,
            self.watched_toggle,
            self.favorite_toggle,
            self.wishlist_toggle,
            self.skipped_toggle,
        ):
            row.addWidget(widget)
        row.addStretch()
        row.addWidget(self.clear_filters_button)

        self.universe_combo.currentIndexChanged.connect(self._on_universe_changed)
        for combo in (self.franchise_combo, self.genre_combo, self.type_combo, self.status_combo, self.character_combo):
            combo.currentIndexChanged.connect(self._on_filters_changed)
        for button in (
            self.watched_toggle,
            self.favorite_toggle,
            self.wishlist_toggle,
            self.skipped_toggle,
        ):
            button.toggled.connect(self._on_filters_changed)

        return row

    def _build_toolbar_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        sort_label = QLabel("Sort:")
        sort_label.setObjectName("inlineLabel")
        self.sort_combo = QComboBox()
        self.sort_combo.setObjectName("filterCombo")
        for label, _field, _direction in SORT_PRESETS:
            self.sort_combo.addItem(label)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)

        row.addWidget(sort_label)
        row.addWidget(self.sort_combo)
        row.addStretch()

        self.result_count_label = QLabel("")
        self.result_count_label.setObjectName("rowSubtitle")
        row.addWidget(self.result_count_label)

        self.view_mode_group = QButtonGroup(self)
        self.view_mode_group.setExclusive(True)
        for mode in VIEW_MODES:
            button = QPushButton(_VIEW_MODE_ICONS[mode])
            button.setObjectName("iconButton")
            button.setToolTip(_VIEW_MODE_TOOLTIPS[mode])
            button.setCheckable(True)
            button.setChecked(mode == self._view_mode)
            button.setProperty("viewMode", mode)
            self.view_mode_group.addButton(button)
            row.addWidget(button)
        self.view_mode_group.buttonClicked.connect(self._on_view_mode_clicked)

        return row

    def _build_pagination_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch()

        self.prev_button = QPushButton("‹ Prev")
        self.prev_button.setObjectName("secondaryButton")
        self.prev_button.clicked.connect(lambda: self.page_changed.emit(self._current_page - 1))

        self.page_label = QLabel("")
        self.page_label.setObjectName("rowSubtitle")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setMinimumWidth(140)

        self.next_button = QPushButton("Next ›")
        self.next_button.setObjectName("secondaryButton")
        self.next_button.clicked.connect(lambda: self.page_changed.emit(self._current_page + 1))

        row.addWidget(self.prev_button)
        row.addWidget(self.page_label)
        row.addWidget(self.next_button)
        row.addStretch()
        return row

    # --- controller-facing API ------------------------------------------------

    def set_filter_options(self, options) -> None:
        """Populate the universe/franchise/genre dropdowns from a duck-typed
        ``services.project_service.FilterOptions``-shaped object."""
        self._suspend_signals = True
        try:
            self._all_franchises = list(options.franchises)

            self.universe_combo.clear()
            self.universe_combo.addItem("All Universes", None)
            for universe_id, name in options.universes:
                self.universe_combo.addItem(name, universe_id)

            self.genre_combo.clear()
            self.genre_combo.addItem("All Genres", None)
            for genre_id, name in options.genres:
                self.genre_combo.addItem(name, genre_id)

            self._rebuild_franchise_combo(selected_universe_id=None)
        finally:
            self._suspend_signals = False

    def set_poster_size_scale(self, scale: float) -> None:
        """Update the Grid/Poster card size multiplier for future
        set_results() rebuilds -- called from MainWindow when Settings >
        Appearance's "Poster Card Size" changes. Doesn't rebuild
        already-rendered cards itself; the controller pairs this with a
        forced Library refresh (see ApplicationController._on_preferences_changed)
        so the change is visible immediately rather than only on next
        natural refresh."""
        self._poster_size_scale = scale

    def set_default_sort(self, sort_field: str, sort_direction: str) -> None:
        """Select whichever SORT_PRESETS entry matches (sort_field,
        sort_direction) without emitting sort_changed -- called once by
        the controller at startup, before the first results load, so the
        combo reflects Settings > Library & Browsing's configured default
        rather than always starting on "Title (A-Z)". Falls back to
        leaving the combo alone if no preset matches."""
        for index, (_label, field, direction) in enumerate(SORT_PRESETS):
            if field == sort_field and direction == sort_direction:
                self._suspend_signals = True
                try:
                    self.sort_combo.setCurrentIndex(index)
                finally:
                    self._suspend_signals = False
                return

    def set_results(self, result, *, filters_active: bool) -> None:
        """Render one page of results. ``result`` is a duck-typed
        ``services.project_service.PagedResult``."""
        self._current_page = result.page

        if result.total_count == 0:
            self.content_stack.hide()
            self.empty_state.show()
            self.empty_state.setText(
                "No projects match your filters.\n"
                "Try clearing a filter or searching for something else."
                if filters_active
                else "Your Marvel library is empty.\nAdd or sync projects to get started."
            )
        else:
            self.empty_state.hide()
            self.content_stack.show()
            self._render_items(result.items)

        count = result.total_count
        self.result_count_label.setText(f"{count} project{'s' if count != 1 else ''}")
        self.page_label.setText(f"Page {result.page} of {result.total_pages}")
        self.prev_button.setEnabled(result.has_previous)
        self.next_button.setEnabled(result.has_next)

    # --- rendering --------------------------------------------------------------

    def _set_grid_container(self) -> None:
        container = QWidget()
        self._flow_layout = FlowLayout(container, margin=0, spacing=16)
        container.setLayout(self._flow_layout)
        self.content_stack.setWidget(container)

    def _set_list_container(self) -> None:
        container = QWidget()
        self._list_layout = QVBoxLayout(container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()
        self.content_stack.setWidget(container)

    def _render_items(self, items) -> None:
        if self._view_mode in ("grid", "poster"):
            self._set_grid_container()
            for item in items:
                card = ProjectCard(
                    item,
                    poster_only=(self._view_mode == "poster"),
                    size_scale=self._poster_size_scale,
                )
                card.clicked.connect(self.project_activated.emit)
                self._flow_layout.addWidget(card)
        else:
            self._set_list_container()
            compact = self._view_mode == "compact"
            for item in items:
                row = ProjectRow(item, compact=compact)
                row.clicked.connect(self.project_activated.emit)
                self._list_layout.insertWidget(self._list_layout.count() - 1, row)

    # --- signal handlers ------------------------------------------------------

    def _rebuild_franchise_combo(self, *, selected_universe_id) -> None:
        self.franchise_combo.clear()
        self.franchise_combo.addItem("All Franchises", None)
        for franchise_id, name, universe_id in self._all_franchises:
            if selected_universe_id is None or universe_id == selected_universe_id:
                self.franchise_combo.addItem(name, franchise_id)

    def _on_universe_changed(self) -> None:
        if self._suspend_signals:
            return
        self._suspend_signals = True
        self._rebuild_franchise_combo(selected_universe_id=self.universe_combo.currentData())
        self._suspend_signals = False
        self._on_filters_changed()

    def _on_filters_changed(self) -> None:
        if self._suspend_signals:
            return
        self.filters_changed.emit(self._current_filters())

    def _current_filters(self) -> dict:
        return {
            "universe_id": self.universe_combo.currentData(),
            "franchise_id": self.franchise_combo.currentData(),
            "genre_id": self.genre_combo.currentData(),
            "project_type": self.type_combo.currentData(),
            "status": self.status_combo.currentData(),
            "character_name": self.character_combo.currentData(),
            "watched": True if self.watched_toggle.isChecked() else None,
            "favorite": True if self.favorite_toggle.isChecked() else None,
            "wishlist": True if self.wishlist_toggle.isChecked() else None,
            "skipped": True if self.skipped_toggle.isChecked() else None,
        }

    def _on_clear_filters(self) -> None:
        self._suspend_signals = True
        try:
            self.universe_combo.setCurrentIndex(0)
            self._rebuild_franchise_combo(selected_universe_id=None)
            self.franchise_combo.setCurrentIndex(0)
            self.genre_combo.setCurrentIndex(0)
            self.type_combo.setCurrentIndex(0)
            self.status_combo.setCurrentIndex(0)
            self.character_combo.setCurrentIndex(0)
            self.watched_toggle.setChecked(False)
            self.favorite_toggle.setChecked(False)
            self.wishlist_toggle.setChecked(False)
            self.skipped_toggle.setChecked(False)
        finally:
            self._suspend_signals = False
        self.clear_filters_requested.emit()

    def _on_sort_changed(self, index: int) -> None:
        if self._suspend_signals or index < 0:
            return
        _label, field, direction = SORT_PRESETS[index]
        self.sort_changed.emit(field, direction)

    def _on_view_mode_clicked(self, button) -> None:
        mode = button.property("viewMode")
        if mode == self._view_mode:
            return
        self._view_mode = mode
        self.view_mode_changed.emit(mode)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Left arrow / A for the previous page, Right arrow / D for the
        next -- only reaches here at all for a key press no currently-
        focused child widget already handled itself (Qt's normal
        "ignored key events bubble up to the parent" behavior), so
        typing "a" or "d" into the search box or a text field is
        completely unaffected; this only fires when focus is on the
        Library page itself, a card, a button, or similar. Clicking an
        already-disabled Prev/Next button (first/last page) is a
        harmless no-op, so no bounds-checking is needed here beyond
        that."""
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_A):
            self.prev_button.click()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_D):
            self.next_button.click()
            event.accept()
            return
        super().keyPressEvent(event)
