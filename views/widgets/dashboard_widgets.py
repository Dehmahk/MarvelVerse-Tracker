from __future__ import annotations

from datetime import date

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from views.formatting import format_long_date
from views.widgets.poster_label import PosterLabel
from views.widgets.project_card import _TYPE_LABELS, _enum_value

# Matches views.styles' DEFAULT_ACCENT -- used as ProgressRing/ActivityBarChart's
# fallback color when no accent is explicitly passed in, so these widgets
# still render sensibly if ever used before an accent color is configured.
_FALLBACK_ACCENT = "#E62429"
_TRACK_COLOR = "#22252C"


class ProgressRing(QWidget):
    """A circular "percent complete" indicator -- Overall Completion's
    modern replacement for a plain "72%" text value. Self-painted (no
    charting library dependency) via QPainter: a muted full-circle track,
    an accent-colored arc for the percent itself, and the number centered
    inside."""

    def __init__(self, diameter: int = 96, accent: str = _FALLBACK_ACCENT, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._percent = 0
        self._accent = accent
        self._diameter = diameter
        self.setFixedSize(diameter, diameter)

    def set_percent(self, percent: int) -> None:
        self._percent = max(0, min(100, percent))
        self.update()

    @property
    def percent(self) -> int:
        return self._percent

    def set_accent(self, accent: str) -> None:
        self._accent = accent
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen_width = max(4, self._diameter // 12)
        rect = QRectF(
            pen_width / 2,
            pen_width / 2,
            self._diameter - pen_width,
            self._diameter - pen_width,
        )

        track_pen = QPen(QColor(_TRACK_COLOR))
        track_pen.setWidth(pen_width)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

        if self._percent > 0:
            progress_pen = QPen(QColor(self._accent))
            progress_pen.setWidth(pen_width)
            progress_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(progress_pen)
            # Qt angles start at 3 o'clock and go counter-clockwise, so
            # start at 12 o'clock (90*16) and sweep clockwise (negative
            # span) for a normal "filling up" progress-ring look.
            span = -int(360 * 16 * (self._percent / 100))
            painter.drawArc(rect, 90 * 16, span)

        painter.setPen(QColor("#FFFFFF"))
        font = QFont()
        font.setPixelSize(max(12, self._diameter // 5))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self._percent}%")
        painter.end()


class ActivityBarChart(QWidget):
    """A simple monthly watch-activity bar chart -- self-painted, same
    "no charting library" approach as ProgressRing. Takes a tuple of
    duck-typed services.statistics_service.MonthlyActivity objects."""

    def __init__(self, accent: str = _FALLBACK_ACCENT, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._months: tuple = ()
        self._accent = accent
        self.setMinimumHeight(120)

    def set_months(self, months) -> None:
        self._months = tuple(months)
        self.update()

    def set_accent(self, accent: str) -> None:
        self._accent = accent
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self._months:
            painter.end()
            return

        label_height = 18
        chart_height = self.height() - label_height
        max_count = max((month.count for month in self._months), default=0) or 1

        count = len(self._months)
        gap = 12
        bar_width = max(8, (self.width() - gap * (count + 1)) / count)

        font = QFont()
        font.setPixelSize(11)
        painter.setFont(font)

        for index, month in enumerate(self._months):
            x = gap + index * (bar_width + gap)
            bar_h = 4 if month.count == 0 else max(6, (month.count / max_count) * (chart_height - 4))
            y = chart_height - bar_h

            color = QColor(_TRACK_COLOR) if month.count == 0 else QColor(self._accent)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(x, y, bar_width, bar_h), 3, 3)

            painter.setPen(QColor("#858A95"))
            painter.drawText(
                QRectF(x, chart_height + 2, bar_width, label_height),
                Qt.AlignmentFlag.AlignCenter,
                month.month_label,
            )
        painter.end()


class BreakdownRow(QWidget):
    """One labeled progress bar -- shared by the Universe Progress panel
    (colored per-universe via `color`) and the Genre Breakdown panel
    (uncolored, using the app's own accent via the shared
    achievementProgress QSS class)."""

    def __init__(self, label: str, percent: int, detail: str, color: str | None = None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        name_label = QLabel(label)
        name_label.setObjectName("rowTitle")
        header.addWidget(name_label)
        header.addStretch()
        detail_label = QLabel(detail)
        detail_label.setObjectName("rowSubtitle")
        header.addWidget(detail_label)
        layout.addLayout(header)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(max(0, min(100, percent)))
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        if color:
            # Sets every visual property on this instance, not just the
            # chunk color -- see settings_view._update_accent_swatch's
            # docstring for why a partial instance-level stylesheet
            # (background only) can render inconsistently when mixed
            # with an app-level stylesheet for the same widget class.
            bar.setStyleSheet(
                f"QProgressBar {{ background: {_TRACK_COLOR}; border: none; border-radius: 4px; }}"
                f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}"
            )
        else:
            bar.setObjectName("achievementProgress")
        layout.addWidget(bar)


class UpNextCard(QFrame):
    """A call-to-action spotlight for the single suggested "watch this
    next" project, in chronological order. Takes a duck-typed
    services.statistics_service.UpNextItem."""

    clicked = Signal(int)

    def __init__(self, item, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("upNextCard")
        self._project_id = item.project_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        poster = PosterLabel(corner_radius=8)
        poster.setFixedSize(56, 84)
        poster.set_poster(item.poster_path, item.title)
        layout.addWidget(poster)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        eyebrow = QLabel("UP NEXT")
        eyebrow.setObjectName("upNextEyebrow")
        text_col.addWidget(eyebrow)

        title = QLabel(item.title)
        title.setObjectName("upNextTitle")
        title.setWordWrap(True)
        text_col.addWidget(title)

        subtitle = QLabel(_TYPE_LABELS.get(_enum_value(item.project_type), ""))
        subtitle.setObjectName("rowSubtitle")
        text_col.addWidget(subtitle)

        text_col.addStretch()
        layout.addLayout(text_col, 1)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._project_id)
        super().mousePressEvent(event)


def _countdown_text(release_date: date | None) -> str | None:
    """"in 12 days" / "Tomorrow!" / "Today!" for an upcoming release, or
    None for an undated ("TBA") one -- there's nothing to count down to.
    Never returns a negative countdown: get_dashboard_stats() already
    filters upcoming_releases down to release_date is None or in the
    future, but this stays defensive in case a chip is ever built from
    stale data some other way."""
    if release_date is None:
        return None
    days = (release_date - date.today()).days
    if days < 0:
        return None
    if days == 0:
        return "Today!"
    if days == 1:
        return "Tomorrow!"
    return f"in {days} days"


class UpcomingReleaseChip(QFrame):
    """One small poster+title+date tile in the Dashboard's "Coming Soon"
    strip. Takes a duck-typed services.statistics_service.UpcomingRelease."""

    clicked = Signal(int)

    def __init__(self, item, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("upcomingChip")
        self._project_id = item.project_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        poster = PosterLabel(corner_radius=8)
        poster.setFixedSize(104, 104)
        poster.set_poster(item.poster_path, item.title)
        layout.addWidget(poster, 0, Qt.AlignmentFlag.AlignHCenter)

        title = QLabel(item.title)
        title.setObjectName("upcomingChipTitle")
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        date_label = QLabel(format_long_date(item.release_date) if item.release_date else "TBA")
        date_label.setObjectName("rowSubtitle")
        date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(date_label)

        countdown_text = _countdown_text(item.release_date)
        if countdown_text:
            countdown_label = QLabel(countdown_text)
            countdown_label.setObjectName("upcomingChipCountdown")
            countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(countdown_label)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._project_id)
        super().mousePressEvent(event)


class CollectionSpotlightCard(QFrame):
    """A small preview of one Collection, encouraging a visit to the
    Collections page. Takes a duck-typed
    services.collection_service.CollectionSummary."""

    view_collection_clicked = Signal(int)

    def __init__(self, summary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("contentPanel")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        eyebrow = QLabel("FROM YOUR COLLECTIONS")
        eyebrow.setObjectName("statTitle")
        text_col.addWidget(eyebrow)

        name = QLabel(summary.name)
        name.setObjectName("sectionHeading")
        text_col.addWidget(name)

        subtitle = QLabel(
            f"{summary.project_count} project{'s' if summary.project_count != 1 else ''}"
            + (f" -- {summary.description}" if summary.description else "")
        )
        subtitle.setObjectName("rowSubtitle")
        subtitle.setWordWrap(True)
        text_col.addWidget(subtitle)

        layout.addLayout(text_col, 1)

        view_button = QPushButton("View Collection")
        view_button.setObjectName("secondaryButton")
        view_button.setCursor(Qt.CursorShape.PointingHandCursor)
        view_button.clicked.connect(lambda: self.view_collection_clicked.emit(summary.id))
        layout.addWidget(view_button, 0, Qt.AlignmentFlag.AlignVCenter)
