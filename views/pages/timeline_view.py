from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from views.widgets.timeline_marker import TimelineMarker


class TimelineView(QWidget):
    """Browse Marvel projects in chronological order, grouped by
    saga/phase. Presentation-only, like every other page: it starts
    empty and is brought to life by the controller calling
    set_filter_options()/set_groups() with duck-typed
    services.timeline_service objects -- this view never imports the
    database or services layer directly.
    """

    project_activated = Signal(int)
    universe_changed = Signal(object)  # int | None
    sort_mode_changed = Signal(str)  # "phase" | "chronological"

    def __init__(self) -> None:
        super().__init__()

        self._suspend_signals = False
        # Which (saga, phase) groups are currently collapsed. Kept here
        # (rather than on the section widgets themselves) because
        # set_groups() tears down and rebuilds the whole container on
        # every refresh -- storing state on this dict, keyed by the
        # group's identity rather than its position, is what lets a
        # collapsed section stay collapsed across those rebuilds.
        self._collapsed_groups: set[tuple[str | None, str | None]] = set()
        # Which sort mode the toolbar is currently set to. Lives here
        # (rather than being inferred from the shape of whatever
        # set_groups() is handed) so the view can decide -- on its own,
        # independent of what the controller/service send it -- whether
        # to render collapsible phase sections or one flat, header-free
        # run of markers.
        self._sort_mode = "phase"
        # The last groups set_groups() was actually handed -- lets
        # Collapse All / Expand All re-render locally (same "no new
        # backend call needed" pattern Achievements' sort toggle and the
        # Dashboard's Universe/Phase toggle already use) rather than
        # waiting on the controller to re-fetch and re-push the exact
        # same data.
        self._last_groups: tuple = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 32)
        layout.setSpacing(16)

        heading = QLabel("Timeline")
        heading.setObjectName("pageHeading")
        subtitle = QLabel("Explore Marvel projects in chronological order.")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(heading)
        layout.addWidget(subtitle)

        layout.addLayout(self._build_filter_row())

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("libraryScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self.scroll_area, 1)

        self.empty_state = QLabel("")
        self.empty_state.setObjectName("emptyState")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.hide()
        layout.addWidget(self.empty_state)

        self._set_container()
        self._update_collapse_buttons_visibility()

    # --- construction helpers ------------------------------------------------

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        universe_label = QLabel("Universe:")
        universe_label.setObjectName("inlineLabel")
        self.universe_combo = QComboBox()
        self.universe_combo.setObjectName("filterCombo")
        self.universe_combo.addItem("All Universes", None)
        self.universe_combo.currentIndexChanged.connect(self._on_universe_changed)

        row.addWidget(universe_label)
        row.addWidget(self.universe_combo)

        sort_label = QLabel("Sort by:")
        sort_label.setObjectName("inlineLabel")
        self.sort_combo = QComboBox()
        self.sort_combo.setObjectName("filterCombo")
        self.sort_combo.addItem("Phase", "phase")
        self.sort_combo.addItem("Chronological Order", "chronological")
        self.sort_combo.currentIndexChanged.connect(self._on_sort_mode_changed)

        row.addWidget(sort_label)
        row.addWidget(self.sort_combo)

        self.collapse_all_button = QPushButton("Collapse All")
        self.collapse_all_button.setObjectName("secondaryButton")
        self.collapse_all_button.clicked.connect(self._on_collapse_all_clicked)
        row.addWidget(self.collapse_all_button)

        self.expand_all_button = QPushButton("Expand All")
        self.expand_all_button.setObjectName("secondaryButton")
        self.expand_all_button.clicked.connect(self._on_expand_all_clicked)
        row.addWidget(self.expand_all_button)

        row.addStretch()
        return row

    def _set_container(self) -> None:
        # A fresh container each render, same pattern LibraryView uses for
        # its grid/list containers -- QScrollArea.setWidget() takes
        # ownership of (and schedules deletion of) whatever widget it's
        # replacing, so old markers never leak.
        container = QWidget()
        self._container_layout = QVBoxLayout(container)
        self._container_layout.setContentsMargins(0, 0, 0, 4)
        self._container_layout.setSpacing(24)
        self._container_layout.addStretch()
        self.scroll_area.setWidget(container)

    # --- controller-facing API ------------------------------------------------

    def set_filter_options(self, options) -> None:
        """Populate the universe filter from a duck-typed
        ``services.project_service.FilterOptions``-shaped object (the
        same one the Library uses -- Timeline only needs the universe
        list from it)."""
        self._suspend_signals = True
        try:
            self.universe_combo.clear()
            self.universe_combo.addItem("All Universes", None)
            for universe_id, name in options.universes:
                self.universe_combo.addItem(name, universe_id)
        finally:
            self._suspend_signals = False

    def set_groups(self, groups) -> None:
        """Render the timeline from a tuple of duck-typed
        ``services.timeline_service.TimelineGroup`` objects, newest
        construction always replacing whatever was rendered before."""
        self._last_groups = tuple(groups)
        self._set_container()

        if not groups:
            self.scroll_area.hide()
            self.empty_state.show()
            self.empty_state.setText(
                "Nothing to show on the timeline yet.\n"
                "Projects need a chronological order or release date to appear here."
            )
            return

        self.empty_state.hide()
        self.scroll_area.show()

        if self._sort_mode == "chronological":
            self._render_flat(groups)
        else:
            self._render_grouped(groups)

    # --- rendering helpers ------------------------------------------------------

    def _render_grouped(self, groups) -> None:
        """The default view: a collapsible, headed section per
        saga/phase group, in the order the groups were handed to us."""
        for group in groups:
            key = (group.saga, group.phase)
            collapsed = key in self._collapsed_groups

            section = QVBoxLayout()
            section.setSpacing(10)

            entries_container = QWidget()
            entries_layout = QVBoxLayout(entries_container)
            entries_layout.setContentsMargins(0, 0, 0, 0)
            entries_layout.setSpacing(10)
            for entry in group.entries:
                marker = TimelineMarker(entry)
                marker.clicked.connect(self.project_activated.emit)
                entries_layout.addWidget(marker)
            entries_container.setVisible(not collapsed)

            header = self._build_section_header(group, collapsed, entries_container, key)
            section.addWidget(header)
            section.addWidget(entries_container)

            self._container_layout.insertLayout(self._container_layout.count() - 1, section)

    def _render_flat(self, groups) -> None:
        """Chronological Order mode: one uninterrupted run of markers,
        numbered by their chronological_order badge, with no phase
        headers or collapsing -- flattens every group's entries into a
        single list, in whatever order they arrived in (the service
        already hands back one ungrouped TimelineGroup for this mode,
        but flattening defensively here keeps this view correct even if
        that ever changes)."""
        for group in groups:
            for entry in group.entries:
                marker = TimelineMarker(entry)
                marker.clicked.connect(self.project_activated.emit)
                self._container_layout.insertWidget(self._container_layout.count() - 1, marker)

    def _build_section_header(
        self,
        group,
        collapsed: bool,
        entries_container: QWidget,
        key: tuple[str | None, str | None],
    ) -> QToolButton:
        """A clickable, checkable header that toggles ``entries_container``'s
        visibility and remembers the collapsed/expanded state in
        ``self._collapsed_groups`` so it survives the next set_groups()
        rebuild."""
        header = QToolButton()
        header.setObjectName("timelineGroupHeading")
        header.setCheckable(True)
        header.setChecked(not collapsed)
        header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        header.setArrowType(Qt.ArrowType.DownArrow if not collapsed else Qt.ArrowType.RightArrow)
        header.setText(self._group_header_text(group))
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header.setCursor(Qt.CursorShape.PointingHandCursor)

        def _on_toggled(expanded: bool) -> None:
            entries_container.setVisible(expanded)
            header.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
            if expanded:
                self._collapsed_groups.discard(key)
            else:
                self._collapsed_groups.add(key)

        header.toggled.connect(_on_toggled)
        return header

    @staticmethod
    def _group_header_text(group) -> str:
        bits = [bit for bit in (group.phase, group.saga) if bit]
        return "  ·  ".join(bits) if bits else "Ungrouped"

    # --- signal handlers ------------------------------------------------------

    def _on_universe_changed(self) -> None:
        if self._suspend_signals:
            return
        self.universe_changed.emit(self.universe_combo.currentData())

    def _on_sort_mode_changed(self) -> None:
        if self._suspend_signals:
            return
        self._sort_mode = self.sort_combo.currentData()
        self._update_collapse_buttons_visibility()
        self.sort_mode_changed.emit(self._sort_mode)

    def _update_collapse_buttons_visibility(self) -> None:
        """Collapsing only means anything in Phase mode's sectioned
        view -- Chronological mode is one flat, header-free run of
        markers with nothing to collapse."""
        is_phase_mode = self._sort_mode != "chronological"
        self.collapse_all_button.setVisible(is_phase_mode)
        self.expand_all_button.setVisible(is_phase_mode)

    def _on_collapse_all_clicked(self) -> None:
        self._collapsed_groups = {(group.saga, group.phase) for group in self._last_groups}
        self.set_groups(self._last_groups)

    def _on_expand_all_clicked(self) -> None:
        self._collapsed_groups.clear()
        self.set_groups(self._last_groups)
