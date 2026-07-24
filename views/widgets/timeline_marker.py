from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from views.widgets.project_card import _TYPE_LABELS, _enum_value
from views.formatting import format_rating
from views.widgets.poster_label import PosterLabel


class TimelineMarker(QFrame):
    """A single entry on the Timeline page.

    Reuses the Library row's visual language (poster placeholder, title,
    rating) but adds a chronological-order badge and visually
    distinguishes watched from unwatched projects, using the same
    ``UserProjectData``-backed fields the Library and Dashboard already
    surface. Takes a duck-typed
    ``services.timeline_service.TimelineEntry``-shaped object -- this
    module never imports the services layer directly, per the "views
    never touch the database or services layer" architecture rule.
    """

    clicked = Signal(int)

    def __init__(self, item, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("timelineMarker")
        self.setProperty("watched", bool(item.watched))
        self._project_id = item.id
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(14, 10, 14, 10)

        order_text = (
            str(item.chronological_order) if item.chronological_order is not None else "—"
        )
        order_badge = QLabel(order_text)
        order_badge.setObjectName("timelineOrderBadge")
        order_badge.setFixedWidth(32)
        order_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(order_badge, 0, Qt.AlignmentFlag.AlignVCenter)

        thumb = PosterLabel(corner_radius=6)
        thumb.setObjectName("rowPosterPlaceholder")
        thumb.setFixedSize(48, 48)
        thumb.set_poster(getattr(item, "poster_path", None), item.title)
        layout.addWidget(thumb)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title = QLabel(item.title)
        title.setObjectName("rowTitle")
        text_col.addWidget(title)

        subtitle_bits = [self._year_text(item), _TYPE_LABELS.get(_enum_value(item.project_type), "")]
        subtitle = QLabel("  ·  ".join(bit for bit in subtitle_bits if bit))
        subtitle.setObjectName("rowSubtitle")
        text_col.addWidget(subtitle)

        layout.addLayout(text_col, 1)

        rating = QLabel(format_rating(item.rating))
        rating.setObjectName("rowRating")
        rating.setFixedWidth(56)
        layout.addWidget(rating, 0, Qt.AlignmentFlag.AlignVCenter)

        watched_mark = QLabel(self._watched_text(item))
        watched_mark.setObjectName(
            "timelineWatchedIndicator" if item.watched else "timelineUnwatchedIndicator"
        )
        watched_mark.setFixedWidth(32)
        watched_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(watched_mark, 0, Qt.AlignmentFlag.AlignVCenter)

    @staticmethod
    def _poster_placeholder_text(title: str) -> str:
        words = [w for w in title.split() if w]
        return "".join(w[0].upper() for w in words[:2]) or "?"

    @staticmethod
    def _year_text(item) -> str:
        return str(item.release_date.year) if item.release_date else "TBA"

    @staticmethod
    def _watched_text(item) -> str:
        mark = "✓" if item.watched else "○"
        return f"★ {mark}" if item.favorite else mark

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._project_id)
