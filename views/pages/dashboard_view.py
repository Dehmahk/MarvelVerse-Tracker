from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from settings.defaults import DEFAULT_ACCENT
from views.formatting import format_rating, format_short_date
from views.widgets.dashboard_widgets import (
    ActivityBarChart,
    BreakdownRow,
    CollectionSpotlightCard,
    ProgressRing,
    UpcomingReleaseChip,
    UpNextCard,
)
from views.widgets.flow_layout import FlowLayout
from views.widgets.project_card import _TYPE_LABELS, _enum_value
from views.widgets.poster_label import PosterLabel


# Small emoji icons for each stat card -- purely decorative, same
# "no real icon assets needed" approach the Achievements page's
# _ICON_EMOJI already takes.
_STAT_ICONS = {
    "movies": "\U0001F3AC",
    "tv": "\U0001F4FA",
    "hours": "\u23F1\uFE0F",
    "favorites": "\u2764\uFE0F",
    "achievements": "\U0001F3C6",
}


class StatCard(QFrame):
    """A single dashboard stat tile. Presentation-only: it just renders
    whatever title/value/subtitle it's given and exposes setters so
    DashboardView can refresh the numbers in place without rebuilding
    the grid."""

    def __init__(self, title: str, value: str, subtitle: str, icon: str | None = None) -> None:
        super().__init__()
        self.setObjectName("statCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        title_label = QLabel(title.upper())
        title_label.setObjectName("statTitle")
        header_row.addWidget(title_label)
        header_row.addStretch()

        if icon:
            icon_label = QLabel(icon)
            icon_label.setObjectName("statIcon")
            header_row.addWidget(icon_label)

        layout.addLayout(header_row)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("statValue")

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("statSubtitle")

        layout.addWidget(self.value_label)
        layout.addWidget(self.subtitle_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)

    def set_subtitle(self, subtitle: str) -> None:
        self.subtitle_label.setText(subtitle)


class CompletionHeroCard(QFrame):
    """The "Overall Completion" hero tile: a ProgressRing instead of a
    plain percentage label."""

    def __init__(self, accent: str) -> None:
        super().__init__()
        self.setObjectName("statCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(18)

        self.ring = ProgressRing(diameter=84, accent=accent)
        layout.addWidget(self.ring)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        title_label = QLabel("OVERALL COMPLETION")
        title_label.setObjectName("statTitle")
        text_col.addWidget(title_label)

        self.subtitle_label = QLabel("0 of 0 projects")
        self.subtitle_label.setObjectName("statSubtitle")
        text_col.addWidget(self.subtitle_label)
        text_col.addStretch()

        layout.addLayout(text_col, 1)

    def set_percent(self, percent: int) -> None:
        self.ring.set_percent(percent)

    def set_subtitle(self, subtitle: str) -> None:
        self.subtitle_label.setText(subtitle)

    def set_accent(self, accent: str) -> None:
        self.ring.set_accent(accent)


class RecentWatchRow(QFrame):
    """A single "Recently Watched" (or "Top Rated") row. Takes a
    duck-typed object shaped like
    ``services.statistics_service.RecentWatchItem`` -- like
    ProjectCard/ProjectRow, this view never imports the services layer
    directly, only the controller does."""

    clicked = Signal(int)

    def __init__(self, item, parent: QWidget | None = None, *, show_rewatch: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("projectRowCompact")
        self._project_id = item.project_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(14, 8, 14, 8)

        thumb = PosterLabel(corner_radius=6)
        thumb.setObjectName("rowPosterPlaceholder")
        thumb.setFixedSize(40, 40)
        thumb.set_poster(getattr(item, "poster_path", None), item.title)
        layout.addWidget(thumb)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title = QLabel(item.title)
        title.setObjectName("rowTitle")
        text_col.addWidget(title)

        subtitle_bits = [_TYPE_LABELS.get(_enum_value(item.project_type), "")]
        if show_rewatch and item.is_rewatch:
            subtitle_bits.append("Rewatch")
        subtitle_bits.append(format_short_date(item.watched_at))
        subtitle = QLabel("  \u00b7  ".join(bit for bit in subtitle_bits if bit))
        subtitle.setObjectName("rowSubtitle")
        text_col.addWidget(subtitle)

        layout.addLayout(text_col, 1)

        rating = QLabel(format_rating(item.rating))
        rating.setObjectName("rowRating")
        rating.setFixedWidth(56)
        layout.addWidget(rating, 0, Qt.AlignmentFlag.AlignVCenter)

    @staticmethod
    def _poster_placeholder_text(title: str) -> str:
        words = [w for w in title.split() if w]
        return "".join(w[0].upper() for w in words[:2]) or "?"

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._project_id)
        super().mousePressEvent(event)


class DashboardView(QWidget):
    """The Dashboard page. Presentation-only, like every other page: it
    starts in a zero/empty state and is brought to life by the controller
    calling set_stats() with a services.statistics_service.DashboardStats
    (duck-typed, never imported directly).

    Closest-to-unlocking achievement and Collections spotlight are pushed
    in separately via set_closest_achievement()/set_collection_spotlight()
    -- they come from achievement_service/collection_service, which this
    page has no business importing (only the controller touches services),
    so those live as their own small setters alongside the main
    DashboardStats-driven set_stats().
    """

    project_activated = Signal(int)
    collection_activated = Signal(int)

    def __init__(self, accent_color: str = DEFAULT_ACCENT) -> None:
        super().__init__()
        self._accent_color = accent_color or DEFAULT_ACCENT
        self._universe_breakdown: tuple = ()
        self._phase_breakdown: tuple = ()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 20)
        outer.setSpacing(16)

        heading = QLabel("Dashboard")
        heading.setObjectName("pageHeading")
        subtitle = QLabel("Your Marvel journey at a glance.")
        subtitle.setObjectName("pageSubtitle")
        outer.addWidget(heading)
        outer.addWidget(subtitle)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("libraryScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self.scroll_area, 1)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 4, 20)
        layout.setSpacing(20)

        # --- hero row: completion ring, up next, closest achievement -----
        hero_row = QHBoxLayout()
        hero_row.setSpacing(16)

        self.completion_card = CompletionHeroCard(self._accent_color)
        hero_row.addWidget(self.completion_card, 1)

        self._up_next_slot = QVBoxLayout()
        self._up_next_placeholder = self._build_placeholder_card("Keep browsing to find what's next.")
        self._up_next_slot.addWidget(self._up_next_placeholder)
        hero_row.addLayout(self._up_next_slot, 1)

        self._achievement_slot = QVBoxLayout()
        self._achievement_placeholder = self._build_placeholder_card("No achievement in progress yet.")
        self._achievement_slot.addWidget(self._achievement_placeholder)
        hero_row.addLayout(self._achievement_slot, 1)

        layout.addLayout(hero_row)

        # --- stat card grid ------------------------------------------------
        stats_grid = QGridLayout()
        stats_grid.setSpacing(16)

        self.movies_card = StatCard("Movies Watched", "0", "No movies watched", _STAT_ICONS["movies"])
        self.tv_card = StatCard("TV Watched", "0", "No shows watched", _STAT_ICONS["tv"])
        self.hours_card = StatCard("Hours Watched", "0h", "Start your journey", _STAT_ICONS["hours"])
        self.favorites_card = StatCard("Favorites", "0", "No favorites yet", _STAT_ICONS["favorites"])
        self.achievements_card = StatCard(
            "Achievements", "0", "Keep watching", _STAT_ICONS["achievements"]
        )

        cards = [
            self.movies_card,
            self.tv_card,
            self.hours_card,
            self.favorites_card,
            self.achievements_card,
        ]
        for index, card in enumerate(cards):
            stats_grid.addWidget(card, index // 5, index % 5)

        layout.addLayout(stats_grid)

        # --- universe/phase progress + genre breakdown ---------------------
        breakdown_row = QHBoxLayout()
        breakdown_row.setSpacing(16)

        (
            self.progress_panel,
            self._progress_layout,
            self.progress_empty_label,
            self.progress_mode_combo,
        ) = self._build_progress_panel()
        self.progress_mode_combo.currentIndexChanged.connect(self._on_progress_mode_changed)
        breakdown_row.addWidget(self.progress_panel, 1)

        self.genre_panel, self._genre_layout, self.genre_empty_label = self._build_breakdown_panel(
            "Top Genres", "Watch something to see your favorite genres."
        )
        breakdown_row.addWidget(self.genre_panel, 1)

        layout.addLayout(breakdown_row)

        # --- activity chart -------------------------------------------------
        activity_panel = QFrame()
        activity_panel.setObjectName("contentPanel")
        activity_layout = QVBoxLayout(activity_panel)
        activity_title = QLabel("Watch Activity")
        activity_title.setObjectName("sectionHeading")
        activity_layout.addWidget(activity_title)
        self.activity_chart = ActivityBarChart(accent=self._accent_color)
        activity_layout.addWidget(self.activity_chart)
        layout.addWidget(activity_panel)

        # --- upcoming releases ------------------------------------------------
        self.upcoming_panel = QFrame()
        self.upcoming_panel.setObjectName("contentPanel")
        upcoming_layout = QVBoxLayout(self.upcoming_panel)
        upcoming_title = QLabel("Coming Soon")
        upcoming_title.setObjectName("sectionHeading")
        upcoming_layout.addWidget(upcoming_title)

        self.upcoming_scroll = QScrollArea()
        self.upcoming_scroll.setObjectName("libraryScrollArea")
        self.upcoming_scroll.setWidgetResizable(True)
        self.upcoming_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.upcoming_scroll.setFixedHeight(190)
        self.upcoming_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.upcoming_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        upcoming_layout.addWidget(self.upcoming_scroll)

        self.upcoming_empty_label = QLabel("Nothing on the horizon yet.")
        self.upcoming_empty_label.setObjectName("emptyState")
        upcoming_layout.addWidget(self.upcoming_empty_label)

        layout.addWidget(self.upcoming_panel)
        self._set_upcoming_container()

        # --- recently watched + top rated --------------------------------
        lists_row = QHBoxLayout()
        lists_row.setSpacing(16)

        recent = QFrame()
        recent.setObjectName("contentPanel")
        recent_layout = QVBoxLayout(recent)
        recent_title = QLabel("Recently Watched")
        recent_title.setObjectName("sectionHeading")
        recent_layout.addWidget(recent_title)
        self._recent_rows_layout = QVBoxLayout()
        self._recent_rows_layout.setSpacing(8)
        recent_layout.addLayout(self._recent_rows_layout)
        self.recent_empty_label = QLabel("Your watch history will appear here.")
        self.recent_empty_label.setObjectName("emptyState")
        recent_layout.addWidget(self.recent_empty_label)
        recent_layout.addStretch()
        lists_row.addWidget(recent, 1)

        top_rated = QFrame()
        top_rated.setObjectName("contentPanel")
        top_rated_layout = QVBoxLayout(top_rated)
        top_rated_title = QLabel("Top Rated By You")
        top_rated_title.setObjectName("sectionHeading")
        top_rated_layout.addWidget(top_rated_title)
        self._top_rated_rows_layout = QVBoxLayout()
        self._top_rated_rows_layout.setSpacing(8)
        top_rated_layout.addLayout(self._top_rated_rows_layout)
        self.top_rated_empty_label = QLabel("Rate something to see your favorites here.")
        self.top_rated_empty_label.setObjectName("emptyState")
        top_rated_layout.addWidget(self.top_rated_empty_label)
        top_rated_layout.addStretch()
        lists_row.addWidget(top_rated, 1)

        layout.addLayout(lists_row)

        # --- collections spotlight -----------------------------------------
        self._collection_spotlight_slot = QVBoxLayout()
        layout.addLayout(self._collection_spotlight_slot)

        layout.addStretch(1)
        self.scroll_area.setWidget(content)

    # --- construction helpers ------------------------------------------------

    @staticmethod
    def _build_placeholder_card(message: str) -> QFrame:
        card = QFrame()
        card.setObjectName("statCard")
        placeholder_layout = QVBoxLayout(card)
        placeholder_layout.setContentsMargins(22, 18, 22, 18)
        label = QLabel(message)
        label.setObjectName("emptyState")
        label.setWordWrap(True)
        placeholder_layout.addWidget(label)
        return card

    @staticmethod
    def _build_breakdown_panel(title: str, empty_message: str) -> tuple[QFrame, QVBoxLayout, QLabel]:
        panel = QFrame()
        panel.setObjectName("contentPanel")
        panel_layout = QVBoxLayout(panel)

        title_label = QLabel(title)
        title_label.setObjectName("sectionHeading")
        panel_layout.addWidget(title_label)

        rows_layout = QVBoxLayout()
        rows_layout.setSpacing(14)
        panel_layout.addLayout(rows_layout)

        empty_label = QLabel(empty_message)
        empty_label.setObjectName("emptyState")
        empty_label.setWordWrap(True)
        panel_layout.addWidget(empty_label)

        return panel, rows_layout, empty_label

    @staticmethod
    def _build_progress_panel() -> tuple[QFrame, QVBoxLayout, QLabel, QComboBox]:
        """Like _build_breakdown_panel, but with a "Universe"/"Phase" mode
        combo in its header instead of a fixed title -- both breakdowns
        are already present in the same DashboardStats set_stats()
        receives, so switching modes is a pure local re-render (see
        _on_progress_mode_changed), same story as Achievements' "Sort by
        Tier"/"Recently Earned" toggle."""
        panel = QFrame()
        panel.setObjectName("contentPanel")
        panel_layout = QVBoxLayout(panel)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        title_label = QLabel("Progress by")
        title_label.setObjectName("sectionHeading")
        header_row.addWidget(title_label)

        mode_combo = QComboBox()
        mode_combo.setObjectName("filterCombo")
        mode_combo.setMinimumWidth(140)
        mode_combo.setFixedHeight(32)
        mode_combo.addItem("Universe", "universe")
        mode_combo.addItem("Phase", "phase")
        header_row.addWidget(mode_combo)
        header_row.addStretch()

        panel_layout.addLayout(header_row)

        rows_layout = QVBoxLayout()
        rows_layout.setSpacing(14)
        panel_layout.addLayout(rows_layout)

        empty_label = QLabel("Watch something to see your progress by universe.")
        empty_label.setObjectName("emptyState")
        empty_label.setWordWrap(True)
        panel_layout.addWidget(empty_label)

        return panel, rows_layout, empty_label, mode_combo

    def _set_upcoming_container(self) -> None:
        container = QWidget()
        self._upcoming_flow = FlowLayout(container, margin=0, spacing=12)
        container.setLayout(self._upcoming_flow)
        self.upcoming_scroll.setWidget(container)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    # --- controller-facing API ---------------------------------------------

    def set_accent_color(self, accent_color: str) -> None:
        """Re-applies a new accent color to the custom-painted widgets
        (ProgressRing, ActivityBarChart) immediately -- called from
        MainWindow when Settings > Appearance saves a new accent. The
        Universe Progress panel's per-universe colors are untouched (they
        aren't accent-derived in the first place), and Genre Breakdown's
        bars pick up the new accent automatically next time set_stats()
        rebuilds them (they're QSS-styled via achievementProgress's
        @ACCENT@, not painted directly)."""
        self._accent_color = accent_color or DEFAULT_ACCENT
        self.completion_card.set_accent(self._accent_color)
        self.activity_chart.set_accent(self._accent_color)

    def set_stats(self, stats) -> None:
        """Refresh every stat card, breakdown panel, and list from a
        duck-typed services.statistics_service.DashboardStats."""
        self.completion_card.set_percent(stats.completion_percent)
        self.completion_card.set_subtitle(f"{stats.watched_count} of {stats.total_projects} projects")

        self.movies_card.set_value(str(stats.movies_watched))
        self.movies_card.set_subtitle(
            "No movies watched" if stats.movies_watched == 0 else f"{stats.movies_watched} logged"
        )

        self.tv_card.set_value(str(stats.tv_watched))
        self.tv_card.set_subtitle(
            "No shows watched" if stats.tv_watched == 0 else f"{stats.tv_watched} logged"
        )

        hours = stats.total_hours_watched
        self.hours_card.set_value(f"{hours:g}h")
        self.hours_card.set_subtitle(
            "Start your journey" if hours == 0 else f"{hours:g} hours logged"
        )

        self.favorites_card.set_value(str(stats.favorite_count))
        self.favorites_card.set_subtitle(
            "No favorites yet" if stats.favorite_count == 0 else f"{stats.favorite_count} favorited"
        )

        self.achievements_card.set_value(str(stats.achievements_unlocked))
        if stats.achievements_total == 0:
            achievements_subtitle = "Coming soon"
        elif stats.achievements_unlocked == 0:
            achievements_subtitle = "Keep watching"
        else:
            achievements_subtitle = f"{stats.achievements_unlocked} of {stats.achievements_total} unlocked"
        self.achievements_card.set_subtitle(achievements_subtitle)

        self._set_up_next(stats.up_next)
        self._set_recently_watched(stats.recently_watched)
        self._set_top_rated(stats.top_rated)
        self._universe_breakdown = stats.universe_breakdown
        self._phase_breakdown = stats.phase_breakdown
        self._render_progress_panel()
        self._set_genre_breakdown(stats.genre_breakdown)
        self.activity_chart.set_months(stats.monthly_activity)
        self._set_upcoming_releases(stats.upcoming_releases)

    def set_closest_achievement(self, status) -> None:
        """`status` is a duck-typed
        services.achievement_service.AchievementStatus for the locked
        achievement closest to unlocking, or None if everything's
        unlocked (or nothing's been synced yet). Reuses
        views.pages.achievements_view.AchievementCard directly for a
        visually identical card, rather than re-implementing it here."""
        self._clear_layout(self._achievement_slot)
        if status is None:
            self._achievement_slot.addWidget(
                self._build_placeholder_card("No achievement in progress yet.")
            )
            return

        from views.pages.achievements_view import AchievementCard

        card = AchievementCard(status)
        # AchievementCard fixes its own width to 260px for the Achievements
        # page's wrap-grid; here it needs to flex with the hero row's
        # stretch factor instead, so reset both bounds back to Qt's
        # defaults (0 and QWIDGETSIZE_MAX) rather than leaving the fixed
        # 260px constraint in place.
        card.setMinimumWidth(0)
        card.setMaximumWidth(16777215)
        self._achievement_slot.addWidget(card)

    def set_collection_spotlight(self, summary) -> None:
        """`summary` is a duck-typed
        services.collection_service.CollectionSummary for the collection
        to spotlight, or None if the user has no collections (or none
        with any projects in them) yet."""
        self._clear_layout(self._collection_spotlight_slot)
        if summary is None:
            return
        card = CollectionSpotlightCard(summary)
        card.view_collection_clicked.connect(self.collection_activated.emit)
        self._collection_spotlight_slot.addWidget(card)

    def _set_up_next(self, item) -> None:
        self._clear_layout(self._up_next_slot)
        if item is None:
            self._up_next_slot.addWidget(
                self._build_placeholder_card("Keep browsing to find what's next.")
            )
            return
        card = UpNextCard(item)
        card.clicked.connect(self.project_activated.emit)
        self._up_next_slot.addWidget(card)

    def _set_recently_watched(self, items) -> None:
        self._clear_layout(self._recent_rows_layout)
        if not items:
            self.recent_empty_label.setVisible(True)
            return
        self.recent_empty_label.setVisible(False)
        for item in items:
            row = RecentWatchRow(item)
            row.clicked.connect(self.project_activated.emit)
            self._recent_rows_layout.addWidget(row)

    def _set_top_rated(self, items) -> None:
        self._clear_layout(self._top_rated_rows_layout)
        if not items:
            self.top_rated_empty_label.setVisible(True)
            return
        self.top_rated_empty_label.setVisible(False)
        for item in items:
            row = RecentWatchRow(item, show_rewatch=False)
            row.clicked.connect(self.project_activated.emit)
            self._top_rated_rows_layout.addWidget(row)

    def _on_progress_mode_changed(self, _index: int) -> None:
        self._render_progress_panel()

    def _render_progress_panel(self) -> None:
        """Render whichever breakdown (Universe or Phase) the mode combo
        currently selects, from the tuples set_stats() already stored --
        a pure local re-render, same "no new backend call needed, both
        sets of data are already on hand" story as Achievements' sort
        toggle. BreakdownRow's `color` is universe-only (phases don't
        have one -- they all render with the shared accent-colored
        achievementProgress bar style instead, same as Genre Breakdown)."""
        mode = self.progress_mode_combo.currentData() or "universe"
        self._clear_layout(self._progress_layout)

        if mode == "phase":
            breakdown = self._phase_breakdown
            rows = [
                BreakdownRow(progress.phase, progress.percent_complete, f"{progress.watched_count} / {progress.total_count}")
                for progress in breakdown
            ]
            empty_message = "Watch something to see your progress by phase."
        else:
            breakdown = self._universe_breakdown
            rows = [
                BreakdownRow(
                    progress.name,
                    progress.percent_complete,
                    f"{progress.watched_count} / {progress.total_count}",
                    color=progress.color_hex,
                )
                for progress in breakdown
            ]
            empty_message = "Watch something to see your progress by universe."

        if not rows:
            self.progress_empty_label.setText(empty_message)
            self.progress_empty_label.setVisible(True)
            return

        self.progress_empty_label.setVisible(False)
        for row in rows:
            self._progress_layout.addWidget(row)

    def _set_genre_breakdown(self, breakdown) -> None:
        self._clear_layout(self._genre_layout)
        if not breakdown:
            self.genre_empty_label.setVisible(True)
            return
        self.genre_empty_label.setVisible(False)
        max_count = max((g.watched_count for g in breakdown), default=0) or 1
        for genre in breakdown:
            percent = round((genre.watched_count / max_count) * 100)
            row = BreakdownRow(genre.name, percent, f"{genre.watched_count} watched")
            self._genre_layout.addWidget(row)

    def _set_upcoming_releases(self, releases) -> None:
        self._set_upcoming_container()
        if not releases:
            self.upcoming_scroll.setVisible(False)
            self.upcoming_empty_label.setVisible(True)
            return
        self.upcoming_scroll.setVisible(True)
        self.upcoming_empty_label.setVisible(False)
        for release in releases:
            chip = UpcomingReleaseChip(release)
            chip.clicked.connect(self.project_activated.emit)
            self._upcoming_flow.addWidget(chip)
