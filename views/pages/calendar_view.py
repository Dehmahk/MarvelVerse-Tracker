from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from views.widgets.poster_label import PosterLabel

_MAX_VISIBLE_PER_DAY = 2


class _CalendarDayCell(QFrame):
    """One day cell in the Calendar grid -- the day number, plus a small
    poster thumbnail per release that day (up to _MAX_VISIBLE_PER_DAY,
    with a "+N more" label for the rest). Empty cells (days outside the
    current month, padding out the grid to whole weeks) are still built
    from this class, just with day_number=None and no releases."""

    project_clicked = Signal(int)

    def __init__(self, day_number: int | None, releases, is_today: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("calendarDayCellToday" if is_today else "calendarDayCell")
        self.setMinimumHeight(90)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        if day_number is None:
            return

        day_label = QLabel(str(day_number))
        day_label.setObjectName("calendarDayNumber")
        layout.addWidget(day_label)

        for release in releases[:_MAX_VISIBLE_PER_DAY]:
            row = QHBoxLayout()
            row.setSpacing(4)

            thumb = PosterLabel(corner_radius=3)
            thumb.setFixedSize(18, 26)
            thumb.set_poster(release.poster_path, release.title)
            thumb.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(thumb)

            title = QLabel(release.title)
            title.setObjectName("calendarReleaseTitle")
            title.setWordWrap(True)
            row.addWidget(title, 1)

            container = QWidget()
            container.setLayout(row)
            container.setCursor(Qt.CursorShape.PointingHandCursor)
            project_id = release.project_id
            container.mousePressEvent = lambda event, pid=project_id: self._on_release_clicked(pid, event)
            layout.addWidget(container)

        remaining = len(releases) - _MAX_VISIBLE_PER_DAY
        if remaining > 0:
            more_label = QLabel(f"+{remaining} more")
            more_label.setObjectName("calendarMoreLabel")
            layout.addWidget(more_label)

        layout.addStretch()

    def _on_release_clicked(self, project_id: int, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.project_clicked.emit(project_id)


class CalendarView(QWidget):
    """Month-by-month calendar of every release in the catalog, past and
    future -- takes a tuple of duck-typed
    services.calendar_service.CalendarProject objects once via
    set_projects(), then handles month navigation entirely locally
    (re-rendering from what's already been fetched), the same "fetch
    once, re-render on navigation" pattern the Achievements sort toggle
    and Dashboard's Universe/Phase toggle already use."""

    project_activated = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._projects: tuple = ()
        self._by_month: dict[tuple[int, int], list] = defaultdict(list)
        today = date.today()
        self._current_year = today.year
        self._current_month = today.month

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 20)
        layout.setSpacing(16)

        heading = QLabel("Calendar")
        heading.setObjectName("pageHeading")
        layout.addWidget(heading)

        subtitle = QLabel("Every release in your library, month by month.")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(subtitle)

        nav_row = QHBoxLayout()
        self.prev_button = QPushButton("‹ Previous")
        self.prev_button.setObjectName("secondaryButton")
        self.prev_button.clicked.connect(self._on_previous_month_clicked)
        nav_row.addWidget(self.prev_button)

        self.month_label = QLabel("")
        self.month_label.setObjectName("sectionHeading")
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_row.addWidget(self.month_label, 1)

        self.today_button = QPushButton("Today")
        self.today_button.setObjectName("secondaryButton")
        self.today_button.clicked.connect(self._on_today_clicked)
        nav_row.addWidget(self.today_button)

        self.next_button = QPushButton("Next ›")
        self.next_button.setObjectName("secondaryButton")
        self.next_button.clicked.connect(self._on_next_month_clicked)
        nav_row.addWidget(self.next_button)

        layout.addLayout(nav_row)

        weekday_row = QHBoxLayout()
        weekday_row.setSpacing(4)
        for name in ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"):
            label = QLabel(name)
            label.setObjectName("rowSubtitle")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            weekday_row.addWidget(label)
        layout.addLayout(weekday_row)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("settingsScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self.scroll_area, 1)

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(4)
        for col in range(7):
            self._grid_layout.setColumnStretch(col, 1)
        self.scroll_area.setWidget(self._grid_container)

        self._render_month()

    def set_projects(self, projects) -> None:
        """Populate every release the Calendar can page through -- called
        once by the controller (or again after a mutating action like a
        TMDB sync changes release dates), not once per month navigation."""
        self._projects = tuple(projects)
        self._by_month = defaultdict(list)
        for project in self._projects:
            key = (project.release_date.year, project.release_date.month)
            self._by_month[key].append(project)
        self._render_month()

    def _clear_grid(self) -> None:
        while self._grid_layout.count():
            child = self._grid_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_month(self) -> None:
        self._clear_grid()

        month_name = date(self._current_year, self._current_month, 1).strftime("%B %Y")
        self.month_label.setText(month_name)

        releases_by_day: dict[int, list] = defaultdict(list)
        for project in self._by_month.get((self._current_year, self._current_month), []):
            releases_by_day[project.release_date.day].append(project)

        today = date.today()
        is_current_month = today.year == self._current_year and today.month == self._current_month

        first_weekday, days_in_month = calendar.monthrange(self._current_year, self._current_month)
        # Python's calendar.monthrange() returns Monday=0; this calendar
        # displays Sunday-first (matching the weekday header row above),
        # so the leading-blank-cell count needs converting from a
        # Monday-first to a Sunday-first week.
        leading_blanks = (first_weekday + 1) % 7

        row = 0
        col = 0
        for _ in range(leading_blanks):
            self._grid_layout.addWidget(_CalendarDayCell(None, [], False), row, col)
            col += 1

        for day in range(1, days_in_month + 1):
            releases = sorted(releases_by_day.get(day, []), key=lambda p: p.title)
            is_today = is_current_month and day == today.day
            cell = _CalendarDayCell(day, releases, is_today)
            cell.project_clicked.connect(self.project_activated.emit)
            self._grid_layout.addWidget(cell, row, col)
            col += 1
            if col == 7:
                col = 0
                row += 1

    def _on_previous_month_clicked(self) -> None:
        self._current_month -= 1
        if self._current_month == 0:
            self._current_month = 12
            self._current_year -= 1
        self._render_month()

    def _on_next_month_clicked(self) -> None:
        self._current_month += 1
        if self._current_month == 13:
            self._current_month = 1
            self._current_year += 1
        self._render_month()

    def _on_today_clicked(self) -> None:
        today = date.today()
        self._current_year = today.year
        self._current_month = today.month
        self._render_month()
