from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from views.formatting import format_long_date
from views.widgets.poster_label import PosterLabel
from views.widgets.project_card import _TYPE_LABELS, _enum_value


class PersonCreditRow(QFrame):
    """One project row in an Actor/Director Details page's credit list --
    a small poster thumbnail, the project's title, its type, release
    year, and this person's character/role on it. Takes a duck-typed
    services.person_service.PersonCredit."""

    clicked = Signal(int)

    def __init__(self, credit, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("watchHistoryEntry")
        self._project_id = credit.project_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        poster = PosterLabel(corner_radius=6)
        poster.setFixedSize(40, 60)
        poster.set_poster(credit.poster_path, credit.title)
        layout.addWidget(poster)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title = QLabel(credit.title)
        title.setObjectName("rowTitle")
        title.setWordWrap(True)
        text_col.addWidget(title)

        role_text = credit.character_name or credit.crew_role or ""
        year_text = str(credit.release_date.year) if credit.release_date else "TBA"
        type_label = _TYPE_LABELS.get(_enum_value(credit.project_type), "")
        subtitle = QLabel(f"{role_text} · {type_label} · {year_text}" if role_text else f"{type_label} · {year_text}")
        subtitle.setObjectName("rowSubtitle")
        subtitle.setWordWrap(True)
        text_col.addWidget(subtitle)

        layout.addLayout(text_col, 1)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._project_id)
        super().mousePressEvent(event)


class PersonDetailView(QWidget):
    """Actor/Director Details: bio, photo, and every project in the
    catalog this person is credited on, whether as cast or crew."""

    back_requested = Signal()
    project_activated = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._person_id: int | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 20)
        outer.setSpacing(12)

        back_row = QHBoxLayout()
        self.back_button = QPushButton("‹ Back")
        self.back_button.setObjectName("secondaryButton")
        self.back_button.clicked.connect(self.back_requested.emit)
        back_row.addWidget(self.back_button)
        back_row.addStretch()
        outer.addLayout(back_row)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("settingsScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self.scroll_area, 1)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setSpacing(20)

        self._build_hero_row()
        self._build_credits_panel("Appears In", "cast")
        self._build_credits_panel("Worked On", "crew")

        self.scroll_area.setWidget(content)

    def _build_hero_row(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(24)

        self.photo = PosterLabel(corner_radius=10)
        self.photo.setFixedSize(150, 150)
        row.addWidget(self.photo)

        text_col = QVBoxLayout()
        text_col.setSpacing(8)

        self.name_label = QLabel("")
        self.name_label.setObjectName("pageHeading")
        self.name_label.setWordWrap(True)
        text_col.addWidget(self.name_label)

        self.birthday_label = QLabel("")
        self.birthday_label.setObjectName("statSubtitle")
        text_col.addWidget(self.birthday_label)

        self.credit_count_label = QLabel("")
        self.credit_count_label.setObjectName("statSubtitle")
        text_col.addWidget(self.credit_count_label)

        self.bio_label = QLabel("")
        self.bio_label.setObjectName("emptyState")
        self.bio_label.setWordWrap(True)
        text_col.addWidget(self.bio_label)

        text_col.addStretch()
        row.addLayout(text_col, 1)

        self._content_layout.addLayout(row)

    def _build_credits_panel(self, heading_text: str, kind: str) -> None:
        panel = QFrame()
        panel.setObjectName("contentPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(6)

        heading = QLabel(heading_text)
        heading.setObjectName("sectionHeading")
        layout.addWidget(heading)

        credits_layout = QVBoxLayout()
        credits_layout.setSpacing(2)
        layout.addLayout(credits_layout)

        setattr(self, f"_{kind}_panel", panel)
        setattr(self, f"_{kind}_layout", credits_layout)

        self._content_layout.addWidget(panel)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_credits(self, layout, credits, empty_text: str) -> None:
        self._clear_layout(layout)
        if not credits:
            empty = QLabel(empty_text)
            empty.setObjectName("detailNoData")
            layout.addWidget(empty)
            return
        for credit in credits:
            row = PersonCreditRow(credit)
            row.clicked.connect(self.project_activated.emit)
            layout.addWidget(row)

    # --- controller-facing API ------------------------------------------------

    def set_person(self, detail) -> None:
        """Populate every widget from a duck-typed
        services.person_service.PersonDetail-shaped object."""
        self._person_id = detail.id
        self.name_label.setText(detail.name)
        self.photo.set_poster(detail.photo_path, detail.name)

        self.birthday_label.setText(
            f"Born {format_long_date(detail.birthday)}" if detail.birthday else ""
        )
        self.birthday_label.setVisible(bool(detail.birthday))

        credit_word = "credit" if detail.total_credits == 1 else "credits"
        self.credit_count_label.setText(f"{detail.total_credits} {credit_word} in your library")

        self.bio_label.setText(detail.bio or "No biography available yet.")

        self._render_credits(self._cast_layout, detail.cast_credits, "No cast credits in your library yet.")
        self._crew_panel.setVisible(bool(detail.crew_credits))
        if detail.crew_credits:
            self._render_credits(self._crew_layout, detail.crew_credits, "")

        self.scroll_area.verticalScrollBar().setValue(0)
