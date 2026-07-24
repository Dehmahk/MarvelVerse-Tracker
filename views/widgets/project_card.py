from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QStackedLayout, QVBoxLayout, QWidget

from views.formatting import format_rating
from views.widgets.poster_label import PosterLabel

_TYPE_LABELS = {
    "movie": "Movie",
    "tv_series": "TV Series",
    "tv_special": "TV Special",
    "short": "Short",
    "documentary": "Documentary",
    "animated_series": "Animated Series",
}

_STATUS_LABELS = {
    "released": "Released",
    "upcoming": "Upcoming",
    "announced": "Announced",
    "in_production": "In Production",
    "cancelled": "Cancelled",
}


def _enum_value(value) -> str:
    """Accepts either a plain string or a str-Enum member (as returned by
    the service layer) and normalizes to its underlying string value."""
    return getattr(value, "value", value)


class ProjectCard(QFrame):
    """A single project tile for the Library's Grid and Poster view modes.

    Takes any duck-typed object with the same attributes as
    ``services.project_service.ProjectListItem`` — the view layer never
    imports that module directly, per the "views never touch the database
    or services layer" architecture rule; the controller is the only thing
    that knows about ``ProjectListItem``.
    """

    clicked = Signal(int)

    def __init__(
        self,
        item,
        *,
        poster_only: bool = False,
        size_scale: float = 1.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("projectCard")
        self._project_id = item.id
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("posterOnly", poster_only)

        # Settings > Appearance's "Poster Card Size" scales both these
        # proportionally from their un-scaled defaults (150x220 for
        # Poster-only, 190x190 for Grid), rather than being an absolute
        # pixel size itself -- see views.pages.library_view for how
        # size_scale is derived from the raw px preference.
        base_width = 150 if poster_only else 190
        base_poster_height = 220 if poster_only else 190
        card_width = round(base_width * size_scale)
        poster_height = round(base_poster_height * size_scale)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setFixedWidth(card_width)

        poster = QFrame()
        poster.setObjectName("projectCardPoster")
        poster.setFixedSize(card_width, poster_height)

        # Two layers sharing the same rect: the art (or initials
        # placeholder while it loads) fills the whole tile, and the
        # status badge / favorite+watched chips float on top of it in a
        # transparent overlay -- their semi-opaque chip backgrounds in
        # the QSS were already designed to sit legibly over real artwork.
        stack = QStackedLayout(poster)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)

        self.poster_label = PosterLabel(corner_radius=9)
        self.poster_label.setObjectName("cardPosterPlaceholder")
        self.poster_label.setFixedSize(card_width, poster_height)
        self.poster_label.set_poster(getattr(item, "poster_path", None), item.title)
        stack.addWidget(self.poster_label)

        overlay = QWidget()
        overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setContentsMargins(10, 10, 10, 10)

        badges = QLabel(_STATUS_LABELS.get(_enum_value(item.status), "—"))
        badges.setObjectName("cardStatusBadge")
        badges.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        overlay_layout.addWidget(
            badges, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        overlay_layout.addStretch()

        indicators = QLabel(self._indicator_text(item, include_rating=poster_only))
        indicators.setObjectName("cardIndicators")
        indicators.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        overlay_layout.addWidget(
            indicators, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom
        )

        stack.addWidget(overlay)

        outer.addWidget(poster)

        title = QLabel(item.title)
        title.setObjectName("cardTitle")
        title.setWordWrap(True)
        outer.addWidget(title)

        if not poster_only:
            meta_bits = [b for b in self._meta_parts(item) if b]
            meta = QLabel("  ·  ".join(meta_bits) or "—")
            meta.setObjectName("cardMeta")
            meta.setWordWrap(True)
            outer.addWidget(meta)

        outer.addStretch()

    @staticmethod
    def _poster_placeholder_text(title: str) -> str:
        words = [w for w in title.split() if w]
        letters = "".join(w[0].upper() for w in words[:2])
        return letters or "?"

    @staticmethod
    def _indicator_text(item, *, include_rating: bool = False) -> str:
        marks = []
        if item.favorite:
            marks.append("★")
        if item.watched:
            marks.append("✓")
        if item.skipped:
            marks.append("⏭")
        marks_text = " ".join(marks)

        if not (include_rating and item.rating is not None):
            return marks_text

        # Poster-only cards hide the meta line (title + year/type/rating
        # below the poster) to stay compact, so this is the only place a
        # rating can show at all in that mode. format_rating() already
        # includes its own glyph (e.g. "★ 8.7" on the default 0-10 scale),
        # which would otherwise collide visually with the favorite mark's
        # own "★" if the two were just mashed together -- the "  ·  "
        # separator keeps them read as two distinct pieces of information
        # rather than a doubled-up star.
        rating_text = format_rating(item.rating)
        return f"{marks_text}  ·  {rating_text}" if marks_text else rating_text

    @staticmethod
    def _meta_parts(item) -> list[str]:
        year = str(item.release_date.year) if item.release_date else "TBA"
        type_label = _TYPE_LABELS.get(_enum_value(item.project_type), "")
        rating = format_rating(item.rating) if item.rating is not None else None
        return [year, type_label, rating]

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._project_id)
