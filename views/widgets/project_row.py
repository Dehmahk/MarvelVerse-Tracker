from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from views.widgets.project_card import _STATUS_LABELS, _TYPE_LABELS, _enum_value
from views.formatting import format_rating
from views.widgets.poster_label import PosterLabel


class ProjectRow(QFrame):
    """A single project row for the Library's List and Compact view modes.

    Like :class:`ProjectCard`, this takes a duck-typed
    ``ProjectListItem``-shaped object rather than importing the services
    layer directly.
    """

    clicked = Signal(int)

    def __init__(self, item, *, compact: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("projectRowCompact" if compact else "projectRow")
        self._project_id = item.id
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(14, 8 if compact else 12, 14, 8 if compact else 12)

        thumb_size = 32 if compact else 56
        thumb = PosterLabel(corner_radius=6)
        thumb.setObjectName("rowPosterPlaceholder")
        thumb.setFixedSize(thumb_size, thumb_size)
        thumb.set_poster(getattr(item, "poster_path", None), item.title)
        layout.addWidget(thumb)

        title = QLabel(item.title)
        title.setObjectName("rowTitleCompact" if compact else "rowTitle")

        if compact:
            layout.addWidget(title, 2)
            for text in self._compact_columns(item):
                col = QLabel(text)
                col.setObjectName("rowColumnCompact")
                col.setMinimumWidth(90)
                layout.addWidget(col, 1)
        else:
            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            text_col.addWidget(title)

            subtitle_bits = [b for b in self._subtitle_parts(item) if b]
            subtitle = QLabel("  ·  ".join(subtitle_bits))
            subtitle.setObjectName("rowSubtitle")
            text_col.addWidget(subtitle)

            if item.genre_names:
                genres = QLabel(", ".join(item.genre_names))
                genres.setObjectName("rowGenres")
                text_col.addWidget(genres)

            layout.addLayout(text_col, 2)

            status = QLabel(_STATUS_LABELS.get(_enum_value(item.status), "—"))
            status.setObjectName("rowStatus")
            layout.addWidget(status, 0, Qt.AlignmentFlag.AlignVCenter)

            rating = QLabel(format_rating(item.rating))
            rating.setObjectName("rowRating")
            rating.setFixedWidth(56)
            layout.addWidget(rating, 0, Qt.AlignmentFlag.AlignVCenter)

            indicators = QLabel(self._indicator_text(item))
            indicators.setObjectName("rowIndicators")
            indicators.setFixedWidth(48)
            layout.addWidget(indicators, 0, Qt.AlignmentFlag.AlignVCenter)

    @staticmethod
    def _poster_placeholder_text(title: str) -> str:
        words = [w for w in title.split() if w]
        letters = "".join(w[0].upper() for w in words[:2])
        return letters or "?"

    @staticmethod
    def _indicator_text(item) -> str:
        marks = []
        if item.favorite:
            marks.append("★")
        if item.watched:
            marks.append("✓")
        if item.skipped:
            marks.append("⏭")
        return " ".join(marks) or "—"

    @staticmethod
    def _subtitle_parts(item) -> list[str]:
        year = str(item.release_date.year) if item.release_date else "TBA"
        type_label = _TYPE_LABELS.get(_enum_value(item.project_type), "")
        universe = item.universe_name or ""
        return [year, type_label, universe]

    @staticmethod
    def _compact_columns(item) -> list[str]:
        year = str(item.release_date.year) if item.release_date else "TBA"
        status = _STATUS_LABELS.get(_enum_value(item.status), "—")
        rating = format_rating(item.rating)
        watched = "✓" if item.watched else "—"
        favorite = "★" if item.favorite else "—"
        return [year, status, rating, watched, favorite]

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._project_id)
