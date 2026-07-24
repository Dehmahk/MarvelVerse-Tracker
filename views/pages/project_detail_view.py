from __future__ import annotations

import html
import weakref
from urllib.parse import parse_qs, urlparse

import shiboken6
from PySide6.QtCore import QPoint, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPixmap, QPolygon
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from views import image_loader
from views.formatting import format_long_date
from views.widgets.project_card import _STATUS_LABELS, _TYPE_LABELS, _enum_value
from views.widgets.poster_label import PosterLabel


def _extract_youtube_video_id(url: str | None) -> str | None:
    """Pulls the 11-character video ID out of a YouTube URL, whatever
    format it's in (a full "watch?v=" link, a shortened "youtu.be/"
    link, or an already-embed "embed/" link) -- trailer_url is whatever
    format TMDB (or a human curator) happened to save, and the embedded
    player below needs a bare ID to build its own embed URL from.
    Returns None for anything that doesn't look like a YouTube link at
    all (e.g. a trailer hosted elsewhere), in which case the page falls
    back to the "Watch Trailer" button alone."""
    if not url:
        return None

    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")

    if host == "youtu.be":
        video_id = parsed.path.lstrip("/")
    elif host in ("youtube.com", "youtube-nocookie.com"):
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith("/embed/"):
            video_id = parsed.path.removeprefix("/embed/")
        elif parsed.path.startswith("/shorts/"):
            video_id = parsed.path.removeprefix("/shorts/")
        else:
            return None
    else:
        return None

    video_id = video_id.split("?")[0].split("&")[0]
    return video_id or None


def _poster_placeholder_text(title: str) -> str:
    words = [w for w in title.split() if w]
    letters = "".join(w[0].upper() for w in words[:2])
    return letters or "?"


def _format_date(value) -> str:
    return format_long_date(value)


def _format_runtime(minutes: int | None) -> str:
    if not minutes:
        return "—"
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


class TrailerThumbnail(QLabel):
    """A clickable YouTube thumbnail with a play-button overlay, opening
    the trailer in the user's default browser when clicked.

    This exists specifically *instead of* embedding an actual player via
    QtWebEngine: that approach was tried first, but QtWebEngine is a
    genuinely heavy dependency (its own Chromium subprocess and large
    resource files) that's known to be troublesome to package with
    PyInstaller -- and in practice it failed hard enough in a packaged
    build to take the whole page down with it, since a native-level
    failure in a bundled Chromium subprocess isn't something a Python
    try/except can catch or recover from.

    This widget carries none of that risk: the thumbnail image is
    fetched through the exact same async, disk-cached image_loader
    used for poster art everywhere else in the app (proven reliable,
    no native subprocess, no Chromium), and "playing" the trailer just
    means opening it in the user's real browser -- the same thing the
    "Watch Trailer" button next to it does.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("trailerThumbnail")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(220)
        self._trailer_url: str | None = None
        self._request_token = 0
        self.hide()

    def set_video(self, video_id: str | None, trailer_url: str | None) -> None:
        """Shows a clickable thumbnail preview for `video_id`, or hides
        this widget entirely if there's no YouTube video to preview.
        Safe to call repeatedly (e.g. once per set_project()) -- a newer
        call always wins over a still-in-flight older thumbnail
        request."""
        self._trailer_url = trailer_url
        self._request_token += 1
        token = self._request_token

        self.setPixmap(QPixmap())
        if video_id is None:
            self.hide()
            return

        self.setText("Loading trailer preview…")
        self.show()

        active_loader = image_loader.loader()
        if active_loader is None:
            self.hide()
            return

        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

        # Weakref + shiboken6.isValid(), same pattern PosterLabel uses --
        # a thumbnail download that completes after this widget's
        # underlying C++ object has already been destroyed (e.g. the
        # user navigated to a different project while it was still in
        # flight) is detected safely instead of risking a crash from
        # touching a dead widget.
        weak_self = weakref.ref(self)

        def _on_ready(pixmap: QPixmap | None) -> None:
            label = weak_self()
            if label is None or not shiboken6.isValid(label):
                return
            if token != label._request_token:
                return
            if pixmap is None or pixmap.isNull():
                label.hide()
                return
            label._apply_pixmap(pixmap)

        active_loader.request(thumbnail_url, _on_ready)

    def _apply_pixmap(self, pixmap: QPixmap) -> None:
        size = self.size()
        if size.width() <= 0 or size.height() <= 0:
            size = self.sizeHint()
        scaled = pixmap.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - size.width()) // 2)
        y = max(0, (scaled.height() - size.height()) // 2)
        cropped = scaled.copy(x, y, size.width(), size.height())

        result = QPixmap(cropped.size())
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(0, 0, cropped)

        center = result.rect().center()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 150))
        radius = 36
        painter.drawEllipse(center, radius, radius)
        painter.setBrush(QColor(255, 255, 255))
        triangle = QPolygon(
            [
                QPoint(center.x() - 12, center.y() - 18),
                QPoint(center.x() - 12, center.y() + 18),
                QPoint(center.x() + 20, center.y()),
            ]
        )
        painter.drawPolygon(triangle)
        painter.end()

        self.setPixmap(result)
        self.setText("")

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._trailer_url and event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(self._trailer_url))
        super().mousePressEvent(event)


class ProjectDetailView(QWidget):
    """Full-page detail view for a single project, reached by clicking a
    card/row in the Library.

    Like every other page, this view never touches the database or
    services layer directly -- it's handed a duck-typed object shaped
    like ``services.project_service.ProjectDetail`` by the controller via
    :meth:`set_project`, and re-emits user edits as primitive-valued
    signals for the controller to persist.
    """

    back_requested = Signal()
    # Emitted when Previous/Next in the Marvel Timeline is clicked --
    # wired the same way project_activated is for every other page (see
    # MainWindow), so this reuses that exact same navigation path rather
    # than needing its own.
    navigate_to_project_requested = Signal(int)
    user_data_field_changed = Signal(int, str, object)
    log_watch_requested = Signal(int)

    def __init__(self, enable_trailer_embed: bool = False) -> None:
        super().__init__()
        self._trailer_embed_enabled = enable_trailer_embed

        self._project_id: int | None = None
        self._trailer_url: str | None = None
        self._previous_project_id: int | None = None
        self._trailer_video_id: str | None = None
        self._next_project_id: int | None = None
        self._suspend_signals = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 20, 32, 20)
        outer.setSpacing(12)

        back_row = QHBoxLayout()
        self.back_button = QPushButton("‹ Back to Library")
        self.back_button.setObjectName("secondaryButton")
        self.back_button.clicked.connect(self.back_requested.emit)
        back_row.addWidget(self.back_button)
        back_row.addStretch()
        outer.addLayout(back_row)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("detailScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self.scroll_area, 1)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(0, 0, 4, 20)
        self._content_layout.setSpacing(20)

        self._build_header()
        self._build_hero_row()
        self._build_synopsis_panel()
        self._build_activity_panel()
        self._build_cast_crew_panel()
        self._build_watch_history_panel()
        self._content_layout.addStretch()

        self.scroll_area.setWidget(content)

    # --- construction helpers ------------------------------------------------

    def _build_header(self) -> None:
        self.title_label = QLabel("")
        self.title_label.setObjectName("pageHeading")
        self.title_label.setWordWrap(True)
        self.subtitle_label = QLabel("")
        self.subtitle_label.setObjectName("pageSubtitle")
        self._content_layout.addWidget(self.title_label)
        self._content_layout.addWidget(self.subtitle_label)

        header_actions = QHBoxLayout()
        self.trailer_button = QPushButton("▶  Watch Trailer")
        self.trailer_button.setObjectName("secondaryButton")
        self.trailer_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.trailer_button.clicked.connect(self._on_trailer_clicked)
        self.trailer_button.hide()  # only shown by set_project() when trailer_url is set
        header_actions.addWidget(self.trailer_button)
        header_actions.addStretch()

        self.previous_timeline_button = QPushButton("←  Previous in Timeline")
        self.previous_timeline_button.setObjectName("secondaryButton")
        self.previous_timeline_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.previous_timeline_button.clicked.connect(self._on_previous_in_timeline_clicked)
        self.previous_timeline_button.hide()
        header_actions.addWidget(self.previous_timeline_button)

        self.next_timeline_button = QPushButton("Next in Timeline  →")
        self.next_timeline_button.setObjectName("secondaryButton")
        self.next_timeline_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_timeline_button.clicked.connect(self._on_next_in_timeline_clicked)
        self.next_timeline_button.hide()
        header_actions.addWidget(self.next_timeline_button)

        self._content_layout.addLayout(header_actions)

        # A clickable YouTube thumbnail preview, shown above the synopsis
        # when trailer_url parses as a YouTube link and the user has
        # opted into this (Settings > Appearance). See TrailerThumbnail's
        # own docstring for why this replaced an earlier QtWebEngine-based
        # embedded player.
        self.trailer_thumbnail = TrailerThumbnail()
        self._content_layout.addWidget(self.trailer_thumbnail)

    def _build_hero_row(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(24)

        poster = QFrame()
        poster.setObjectName("detailPoster")
        poster.setFixedSize(220, 320)

        # Same layered pattern as ProjectCard: real art (or the initials
        # placeholder while it loads) fills the whole poster, with the
        # status badge floating on top in a transparent overlay.
        stack = QStackedLayout(poster)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)

        self.poster_label = PosterLabel(corner_radius=11)
        self.poster_label.setObjectName("detailPosterPlaceholder")
        self.poster_label.setFixedSize(220, 320)
        stack.addWidget(self.poster_label)

        overlay = QWidget()
        overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setContentsMargins(14, 14, 14, 14)

        self.poster_badge = QLabel("")
        self.poster_badge.setObjectName("detailStatusBadge")
        overlay_layout.addWidget(
            self.poster_badge, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        overlay_layout.addStretch()

        stack.addWidget(overlay)

        row.addWidget(poster)

        facts_panel = QFrame()
        facts_panel.setObjectName("contentPanel")
        facts_outer = QVBoxLayout(facts_panel)
        facts_outer.setContentsMargins(22, 18, 22, 18)

        facts_grid = QGridLayout()
        facts_grid.setHorizontalSpacing(28)
        facts_grid.setVerticalSpacing(14)

        fact_defs = [
            ("Release Date", "fact_release"),
            ("In-Universe Date", "fact_in_universe_date"),
            ("Runtime", "fact_runtime"),
            ("Seasons", "fact_season_count"),
            ("Episodes", "fact_episode_count"),
            ("Studio", "fact_studio"),
            ("Universe", "fact_universe"),
            ("Franchise", "fact_franchise"),
            ("Genres", "fact_genres"),
            ("Saga", "fact_saga"),
            ("Phase", "fact_phase"),
            ("Timeline Position", "fact_chronological_order"),
            ("Production Started", "fact_production_start_date"),
            ("Cancelled", "fact_cancelled"),
            ("Next Season", "fact_next_season"),
        ]
        for index, (label_text, attr_name) in enumerate(fact_defs):
            grid_row, grid_col = divmod(index, 2)
            label = QLabel(label_text.upper())
            label.setObjectName("detailFactLabel")
            value = QLabel("—")
            value.setObjectName("detailFactValue")
            value.setWordWrap(True)
            setattr(self, attr_name, value)

            pair = QVBoxLayout()
            pair.setSpacing(2)
            pair.addWidget(label)
            pair.addWidget(value)
            facts_grid.addLayout(pair, grid_row, grid_col)

        facts_outer.addLayout(facts_grid)
        row.addWidget(facts_panel, 1)

        self._content_layout.addLayout(row)

    def _build_synopsis_panel(self) -> None:
        panel = QFrame()
        panel.setObjectName("contentPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 18, 22, 18)

        heading = QLabel("Synopsis")
        heading.setObjectName("sectionHeading")
        layout.addWidget(heading)

        self.synopsis_label = QLabel("")
        self.synopsis_label.setObjectName("detailSynopsis")
        self.synopsis_label.setWordWrap(True)
        layout.addWidget(self.synopsis_label)

        self._content_layout.addWidget(panel)

    def _build_activity_panel(self) -> None:
        panel = QFrame()
        panel.setObjectName("contentPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        heading = QLabel("Your Activity")
        heading.setObjectName("sectionHeading")
        layout.addWidget(heading)

        toggles_row = QHBoxLayout()
        self.watched_toggle = QPushButton("Watched")
        self.favorite_toggle = QPushButton("Favorite")
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
            toggles_row.addWidget(button)
        toggles_row.addStretch()
        layout.addLayout(toggles_row)

        self.watched_toggle.toggled.connect(lambda checked: self._emit_field("watched", checked))
        self.favorite_toggle.toggled.connect(
            lambda checked: self._emit_field("favorite", checked)
        )
        self.wishlist_toggle.toggled.connect(
            lambda checked: self._emit_field("wishlist", checked)
        )
        self.skipped_toggle.toggled.connect(
            lambda checked: self._emit_field("skipped", checked)
        )

        rating_row = QHBoxLayout()
        rating_label = QLabel("Rating:")
        rating_label.setObjectName("inlineLabel")
        self.rating_spin = QDoubleSpinBox()
        self.rating_spin.setObjectName("ratingSpin")
        self.rating_spin.setRange(0.0, 10.0)
        self.rating_spin.setSingleStep(0.5)
        self.rating_spin.setDecimals(1)
        self.rating_spin.editingFinished.connect(self._on_rating_committed)
        self.rating_clear_button = QPushButton("Clear")
        self.rating_clear_button.setObjectName("secondaryButton")
        self.rating_clear_button.clicked.connect(self._on_rating_cleared)
        rating_row.addWidget(rating_label)
        rating_row.addWidget(self.rating_spin)
        rating_row.addWidget(self.rating_clear_button)
        rating_row.addStretch()
        layout.addLayout(rating_row)

        watch_row = QHBoxLayout()
        self.log_watch_button = QPushButton("Log a Watch")
        self.log_watch_button.setObjectName("primaryButton")
        self.log_watch_button.clicked.connect(self._on_log_watch_clicked)
        self.watch_stats_label = QLabel("Not watched yet.")
        self.watch_stats_label.setObjectName("rowSubtitle")
        watch_row.addWidget(self.log_watch_button)
        watch_row.addWidget(self.watch_stats_label)
        watch_row.addStretch()
        layout.addLayout(watch_row)

        notes_label = QLabel("Notes")
        notes_label.setObjectName("inlineLabel")
        self.notes_edit = QTextEdit()
        self.notes_edit.setObjectName("notesEdit")
        self.notes_edit.setFixedHeight(90)
        layout.addWidget(notes_label)
        layout.addWidget(self.notes_edit)

        notes_button_row = QHBoxLayout()
        self.save_notes_button = QPushButton("Save Notes")
        self.save_notes_button.setObjectName("secondaryButton")
        self.save_notes_button.clicked.connect(self._on_save_notes)
        notes_button_row.addStretch()
        notes_button_row.addWidget(self.save_notes_button)
        layout.addLayout(notes_button_row)

        self._content_layout.addWidget(panel)

    def _build_cast_crew_panel(self) -> None:
        panel = QFrame()
        panel.setObjectName("contentPanel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(32)

        cast_col = QVBoxLayout()
        cast_heading = QLabel("Cast")
        cast_heading.setObjectName("sectionHeading")
        cast_col.addWidget(cast_heading)
        self.cast_list_layout = QVBoxLayout()
        self.cast_list_layout.setSpacing(2)
        cast_col.addLayout(self.cast_list_layout)
        cast_col.addStretch()

        crew_col = QVBoxLayout()
        crew_heading = QLabel("Crew")
        crew_heading.setObjectName("sectionHeading")
        crew_col.addWidget(crew_heading)
        self.crew_list_layout = QVBoxLayout()
        self.crew_list_layout.setSpacing(2)
        crew_col.addLayout(self.crew_list_layout)
        crew_col.addStretch()

        layout.addLayout(cast_col, 1)
        layout.addLayout(crew_col, 1)

        self._content_layout.addWidget(panel)

    def _build_watch_history_panel(self) -> None:
        panel = QFrame()
        panel.setObjectName("contentPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(6)

        heading = QLabel("Watch History")
        heading.setObjectName("sectionHeading")
        layout.addWidget(heading)

        self.history_list_layout = QVBoxLayout()
        self.history_list_layout.setSpacing(2)
        layout.addLayout(self.history_list_layout)

        self._content_layout.addWidget(panel)

    # --- controller-facing API ------------------------------------------------

    def set_project(self, detail) -> None:
        """Populate every widget from a duck-typed
        ``services.project_service.ProjectDetail``-shaped object. Signals
        are suspended while widgets are populated so this never re-emits
        the edits it's applying."""
        self._suspend_signals = True
        try:
            self._project_id = detail.id
            self._trailer_url = detail.trailer_url
            self.trailer_button.setVisible(bool(detail.trailer_url))
            self._update_trailer_embed(detail.trailer_url)

            previous = detail.previous_in_timeline
            self._previous_project_id = previous.id if previous else None
            self.previous_timeline_button.setVisible(previous is not None)
            if previous is not None:
                self.previous_timeline_button.setText(f"←  {previous.title}")

            next_ = detail.next_in_timeline
            self._next_project_id = next_.id if next_ else None
            self.next_timeline_button.setVisible(next_ is not None)
            if next_ is not None:
                self.next_timeline_button.setText(f"{next_.title}  →")

            self.title_label.setText(detail.title)
            self.subtitle_label.setText(self._subtitle_text(detail))

            self.poster_badge.setText(_STATUS_LABELS.get(_enum_value(detail.status), "—"))
            self.poster_label.set_poster(detail.poster_path, detail.title)

            self.fact_release.setText(_format_date(detail.release_date))
            self.fact_in_universe_date.setText(detail.in_universe_date or "—")
            self.fact_runtime.setText(_format_runtime(detail.runtime_minutes))
            self.fact_season_count.setText(
                str(detail.season_count) if detail.season_count is not None else "—"
            )
            self.fact_episode_count.setText(
                str(detail.episode_count) if detail.episode_count is not None else "—"
            )
            self.fact_studio.setText(detail.studio or "—")
            self.fact_universe.setText(detail.universe_name or "—")
            self.fact_franchise.setText(detail.franchise_name or "—")
            self.fact_genres.setText(", ".join(detail.genre_names) or "—")
            self.fact_saga.setText(detail.saga or "—")
            self.fact_phase.setText(detail.phase or "—")
            self.fact_chronological_order.setText(
                f"#{detail.chronological_order}" if detail.chronological_order is not None else "—"
            )
            self.fact_production_start_date.setText(
                _format_date(detail.production_start_date)
                if detail.production_start_date is not None
                else "—"
            )
            self.fact_cancelled.setText(
                _format_date(detail.cancelled_date) if detail.cancelled_date is not None else "—"
            )
            self.fact_next_season.setText(
                _format_date(detail.next_season_release_date)
                if detail.next_season_release_date is not None
                else "—"
            )

            self.synopsis_label.setText(detail.synopsis or "No synopsis available yet.")

            self.watched_toggle.setChecked(detail.watched)
            self.favorite_toggle.setChecked(detail.favorite)
            self.wishlist_toggle.setChecked(detail.wishlist)
            self.skipped_toggle.setChecked(detail.skipped)

            self.rating_spin.setValue(detail.rating if detail.rating is not None else 0.0)
            self.notes_edit.setPlainText(detail.notes or "")

            self.log_watch_button.setText("Log a Rewatch" if detail.watched else "Log a Watch")
            self.watch_stats_label.setText(self._watch_stats_text(detail))

            self._render_cast_crew(detail.cast, detail.crew)
            self._render_watch_history(detail.watch_history)
        finally:
            self._suspend_signals = False

    # --- rendering --------------------------------------------------------------

    @staticmethod
    def _subtitle_text(detail) -> str:
        year = str(detail.release_date.year) if detail.release_date else "TBA"
        type_label = _TYPE_LABELS.get(_enum_value(detail.project_type), "")
        status_label = _STATUS_LABELS.get(_enum_value(detail.status), "")
        return "  ·  ".join(part for part in (year, type_label, status_label) if part)

    @staticmethod
    def _watch_stats_text(detail) -> str:
        if not detail.watched:
            return "Not watched yet."
        bits = ["Watched"]
        if detail.rewatch_count:
            plural = "s" if detail.rewatch_count != 1 else ""
            bits.append(f"rewatched {detail.rewatch_count} time{plural}")
        if detail.last_watched_date:
            bits.append(f"last watched {_format_date(detail.last_watched_date)}")
        return " · ".join(bits)

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_cast_crew(self, cast, crew) -> None:
        self._clear_layout(self.cast_list_layout)
        if not cast:
            empty = QLabel("No cast recorded yet.")
            empty.setObjectName("detailNoData")
            self.cast_list_layout.addWidget(empty)
        else:
            for member in cast:
                text = html.escape(member.name)
                if member.character_name:
                    text += (
                        f" <span style='color:#686D78;'>as "
                        f"{html.escape(member.character_name)}</span>"
                    )
                label = QLabel(text)
                label.setObjectName("castCrewEntry")
                label.setWordWrap(True)
                self.cast_list_layout.addWidget(label)

        self._clear_layout(self.crew_list_layout)
        if not crew:
            empty = QLabel("No crew recorded yet.")
            empty.setObjectName("detailNoData")
            self.crew_list_layout.addWidget(empty)
        else:
            for member in crew:
                text = (
                    f"{html.escape(member.name)} "
                    f"<span style='color:#686D78;'>— {html.escape(member.role)}</span>"
                )
                label = QLabel(text)
                label.setObjectName("castCrewEntry")
                label.setWordWrap(True)
                self.crew_list_layout.addWidget(label)

    def _render_watch_history(self, watch_history) -> None:
        self._clear_layout(self.history_list_layout)
        if not watch_history:
            empty = QLabel("No watch history yet.")
            empty.setObjectName("detailNoData")
            self.history_list_layout.addWidget(empty)
            return

        for entry in watch_history:
            verb = "Rewatched" if entry.is_rewatch else "Watched"
            text = f"{verb} on {format_long_date(entry.watched_at)}"
            if entry.notes:
                text += f" — {html.escape(entry.notes)}"
            label = QLabel(text)
            label.setObjectName("watchHistoryEntry")
            label.setWordWrap(True)
            self.history_list_layout.addWidget(label)

    # --- signal handlers ------------------------------------------------------

    def _emit_field(self, field: str, value) -> None:
        if self._suspend_signals or self._project_id is None:
            return
        self.user_data_field_changed.emit(self._project_id, field, value)

    def _on_rating_committed(self) -> None:
        self._emit_field("rating", self.rating_spin.value())

    def _on_rating_cleared(self) -> None:
        self._suspend_signals = True
        try:
            self.rating_spin.setValue(0.0)
        finally:
            self._suspend_signals = False
        self._emit_field("rating", None)

    def _on_save_notes(self) -> None:
        text = self.notes_edit.toPlainText().strip()
        self._emit_field("notes", text or None)

    def _on_log_watch_clicked(self) -> None:
        if self._project_id is not None:
            self.log_watch_requested.emit(self._project_id)

    def _on_trailer_clicked(self) -> None:
        if self._trailer_url:
            QDesktopServices.openUrl(QUrl(self._trailer_url))

    def set_trailer_embed_enabled(self, enabled: bool) -> None:
        """Called by MainWindow when Settings > Appearance's experimental
        trailer-embed toggle changes, so it takes effect immediately on
        whatever project is currently open rather than only the next
        time a project is opened."""
        self._trailer_embed_enabled = enabled
        self._update_trailer_embed(self._trailer_url)

    def _update_trailer_embed(self, trailer_url: str | None) -> None:
        """Shows a clickable trailer thumbnail preview above the synopsis
        when `trailer_url` parses as a YouTube link and the user has
        opted into this (Settings > Appearance) -- otherwise hides it
        entirely and leaves the "Watch Trailer" button (populated
        separately, just above) as the only way to view it. See
        TrailerThumbnail's docstring for why this is a thumbnail-and-
        click rather than an embedded player."""
        self._trailer_video_id = _extract_youtube_video_id(trailer_url)

        if not self._trailer_embed_enabled or self._trailer_video_id is None:
            self.trailer_thumbnail.set_video(None, None)
            return

        self.trailer_thumbnail.set_video(self._trailer_video_id, trailer_url)

    def _on_previous_in_timeline_clicked(self) -> None:
        if self._previous_project_id is not None:
            self.navigate_to_project_requested.emit(self._previous_project_id)

    def _on_next_in_timeline_clicked(self) -> None:
        if self._next_project_id is not None:
            self.navigate_to_project_requested.emit(self._next_project_id)
