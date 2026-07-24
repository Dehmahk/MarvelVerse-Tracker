from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from views.widgets.flow_layout import FlowLayout

# Maps the small icon keys stored in Achievement.icon (see
# database/seed/reference_data.py) to an emoji glyph -- keeps this page
# from needing real icon assets for a first pass. Falls back to a trophy
# for any icon key this page doesn't recognize yet (including no icon at
# all), so a new seeded achievement never renders with a blank/broken
# icon.
_ICON_EMOJI = {
    "footprints": "👣",
    "popcorn": "🍿",
    "star": "⭐",
    "star-half": "🌗",
    "globe": "🌐",
    "refresh": "🔁",
    "clapper": "🎬",
    "tv": "📺",
    "flame": "🔥",
    "spider": "🕷️",
    "dna": "🧬",
    "cassette": "📼",
    "mask": "🎭",
    "shield": "🛡️",
    "replay": "🔂",
    "couch": "🛋️",
    "crown": "👑",
    "notepad": "📝",
    "clipboard": "📋",
    "archive": "🗄️",
    "portal": "🌀",
    "blitz": "⚡",
    "reactor": "⚛️",
    "gem": "💎",
    "ant": "🐜",
    "hammer": "🔨",
    "rocket": "🚀",
    "web": "🕸️",
    "stream": "📡",
    "gauntlet": "🧤",
    "dagger": "🗡️",
    "venom": "🖤",
    "chimichanga": "🌮",
    "skull": "💀",
    "bat": "🦇",
    "scales": "⚖️",
    "four": "4️⃣",
    "smash": "👊",
    "brick": "🧱",
    "hourglass": "⏳",
    "comic": "📖",
    "multiverse": "🌌",
}
_DEFAULT_ICON_EMOJI = "🏆"

# Matches services.achievement_service.AchievementTier's values -- kept as
# plain strings (rather than importing the enum) since this view only
# ever sees a duck-typed AchievementStatus, per the "views never import
# the services layer directly" rule every other page follows.
_TIER_LABELS = {
    "bronze": "Bronze",
    "silver": "Silver",
    "gold": "Gold",
    "platinum": "Platinum",
    "diamond": "Diamond",
    "marvelous": "Marvelous",
}

# Display order for "Sort by Tier" mode's sections -- least to most
# prestigious, with the single Marvelous capstone achievement last since
# it's earned by unlocking everything else. Any tier not in this list
# (shouldn't happen with real seeded data) sorts after all of these,
# alphabetically, rather than being silently dropped.
_TIER_DISPLAY_ORDER = ["bronze", "silver", "gold", "platinum", "diamond", "marvelous"]


class AchievementCard(QFrame):
    """A single achievement tile: icon, name, tier badge, description, a
    progress bar toward the next threshold, and an unlocked/locked
    footer. Takes a duck-typed object shaped like
    ``services.achievement_service.AchievementStatus`` -- like every
    other card/row in this app, this view never imports the services
    layer, only the controller does."""

    def __init__(self, status, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("achievementCard")
        self.setProperty("unlocked", status.is_unlocked)
        self.setFixedWidth(260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        header = QLabel(self._icon_for(status.icon))
        header.setObjectName("achievementIcon")
        header.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(header)

        name = QLabel(status.name)
        name.setObjectName("achievementName")
        name.setWordWrap(True)
        layout.addWidget(name)

        tier_label = _TIER_LABELS.get(_enum_value(status.tier), "")
        tier = QLabel(tier_label)
        tier.setObjectName(f"achievementTier{tier_label}")
        layout.addWidget(tier)

        description = QLabel(status.description or "")
        description.setObjectName("achievementDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("achievementProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(status.percent_complete)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        layout.addWidget(self.progress_bar)

        footer_text = (
            f"Unlocked {status.unlocked_at.strftime('%b %d, %Y')}"
            if status.is_unlocked
            else status.progress_label
        )
        self.footer_label = QLabel(footer_text)
        self.footer_label.setObjectName(
            "achievementFooterUnlocked" if status.is_unlocked else "achievementFooter"
        )
        layout.addWidget(self.footer_label)

    @staticmethod
    def _icon_for(icon_key: str | None) -> str:
        return _ICON_EMOJI.get(icon_key or "", _DEFAULT_ICON_EMOJI)


def _enum_value(value) -> str:
    """Accepts either a real enum member or a plain string for ``tier``,
    same convenience helper pattern as
    ``views.widgets.project_card._enum_value``."""
    return value.value if hasattr(value, "value") else str(value)


def _priority_key(status) -> tuple:
    """Unlocked achievements first (most-recently-unlocked at the top),
    then locked ones ordered by how close they are to unlocking -- same
    tie-breaking services.achievement_service._sort_key uses, just
    without that function's tier component, since callers here have
    either already grouped by tier (Sort by Tier) or are deliberately
    ignoring tier entirely (Sort by Recently Earned)."""
    if status.is_unlocked:
        return (0, -status.unlocked_at.timestamp())
    return (1, -status.percent_complete, status.key)


class TierSectionHeader(QFrame):
    """A section divider for "Sort by Tier" mode: the tier name (colored
    to match that tier's badge, so the page reads as clearly banded
    sections rather than one undifferentiated wall of cards) plus an
    "X of Y unlocked" count for that tier alone."""

    def __init__(self, tier_key: str, unlocked_count: int, total_count: int) -> None:
        super().__init__()
        self.setObjectName("achievementSectionHeader")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        tier_label = _TIER_LABELS.get(tier_key, tier_key.title())
        name = QLabel(tier_label)
        name.setObjectName(f"achievementSectionTitle{tier_label}")
        layout.addWidget(name)

        count = QLabel(f"{unlocked_count} / {total_count} unlocked")
        count.setObjectName("achievementSectionCount")
        layout.addWidget(count)
        layout.addStretch()


class AchievementsView(QWidget):
    """Browse every tracked achievement, unlocked or not. Presentation
    -only, like every other page: it starts empty and is brought to life
    by the controller calling set_achievements() with a tuple of
    duck-typed services.achievement_service.AchievementStatus objects --
    this view never imports the database or services layer directly.

    Sorting ("Sort by Tier" vs "Sort by Recently Earned") is handled
    entirely in this view rather than round-tripped through the
    controller: unlike Timeline's Phase/Chronological modes, both of
    these sort orders are pure rearrangements of the exact same data
    set_achievements() already received, so there's nothing for the
    service layer to recompute or re-fetch. The view just keeps the last
    statuses it was given and re-renders locally when the combo changes.
    """

    def __init__(self) -> None:
        super().__init__()
        self._statuses: tuple = ()
        self._sort_mode = "tier"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 32)
        layout.setSpacing(16)

        heading = QLabel("Achievements")
        heading.setObjectName("pageHeading")
        subtitle = QLabel("Track your progress across the Marvel-verse.")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(heading)
        layout.addWidget(subtitle)

        toolbar_row = QHBoxLayout()
        toolbar_row.setSpacing(10)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("statSubtitle")
        toolbar_row.addWidget(self.summary_label)
        toolbar_row.addStretch()

        sort_label = QLabel("Sort:")
        sort_label.setObjectName("inlineLabel")
        toolbar_row.addWidget(sort_label)

        self.sort_combo = QComboBox()
        self.sort_combo.setObjectName("filterCombo")
        self.sort_combo.setMinimumWidth(180)
        self.sort_combo.setFixedHeight(36)
        self.sort_combo.addItem("Tier", "tier")
        self.sort_combo.addItem("Recently Earned", "recent")
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        toolbar_row.addWidget(self.sort_combo)

        layout.addLayout(toolbar_row)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("libraryScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self.scroll_area, 1)

        self.empty_state = QLabel("No achievements are defined yet.")
        self.empty_state.setObjectName("emptyState")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.hide()
        layout.addWidget(self.empty_state)

        # A blank placeholder until the controller's first
        # set_achievements() call -- deliberately not running that method
        # (or _render()) here, so a freshly-built page doesn't flash the
        # "No achievements are defined yet." empty state before real data
        # has even had a chance to load.
        self.scroll_area.setWidget(QWidget())

    def _on_sort_changed(self, _index: int) -> None:
        self._sort_mode = self.sort_combo.currentData() or "tier"
        self._render()

    def _new_flow_container(self) -> QWidget:
        """A plain widget with its own FlowLayout, ready to have
        AchievementCards added to it -- used once for the whole page in
        "Recently Earned" mode, and once per tier section in "Tier"
        mode."""
        container = QWidget()
        flow = FlowLayout(container, margin=0, spacing=16)
        container.setLayout(flow)
        return container

    def _render(self) -> None:
        """Rebuild the whole scroll area's contents from self._statuses
        in the current sort mode. A fresh container every time, same
        pattern the Library grid and Timeline sections use --
        QScrollArea.setWidget() takes ownership of (and schedules
        deletion of) whatever widget it's replacing, so old cards never
        leak."""
        statuses = self._statuses

        if not statuses:
            self.scroll_area.setWidget(QWidget())
            self.scroll_area.hide()
            self.empty_state.show()
            self.summary_label.setText("")
            return

        self.empty_state.hide()
        self.scroll_area.show()

        unlocked_count = sum(1 for status in statuses if status.is_unlocked)
        self.summary_label.setText(f"{unlocked_count} of {len(statuses)} unlocked")

        if self._sort_mode == "recent":
            self.scroll_area.setWidget(self._render_recent(statuses))
        else:
            self.scroll_area.setWidget(self._render_by_tier(statuses))

    def _render_recent(self, statuses) -> QWidget:
        """Sort by Recently Earned: one flat, unsectioned wrap-grid --
        unlocked achievements first (most recent at the top), then
        locked ones ordered by how close they are to unlocking."""
        container = self._new_flow_container()
        for status in sorted(statuses, key=_priority_key):
            container.layout().addWidget(AchievementCard(status))
        return container

    def _render_by_tier(self, statuses) -> QWidget:
        """Sort by Tier: a clearly separated section per tier (Bronze
        through Marvelous, in that order), each with its own header and
        its own wrap-grid, so the different tiers read as distinct bands
        rather than blending into one undifferentiated wall of cards."""
        by_tier: dict[str, list] = {}
        for status in statuses:
            tier_key = _enum_value(status.tier)
            by_tier.setdefault(tier_key, []).append(status)

        ordered_tier_keys = sorted(
            by_tier.keys(),
            key=lambda key: (
                _TIER_DISPLAY_ORDER.index(key) if key in _TIER_DISPLAY_ORDER else len(_TIER_DISPLAY_ORDER),
                key,
            ),
        )

        container = QWidget()
        section_layout = QVBoxLayout(container)
        section_layout.setContentsMargins(0, 0, 4, 0)
        section_layout.setSpacing(20)

        for tier_key in ordered_tier_keys:
            tier_statuses = by_tier[tier_key]
            unlocked_in_tier = sum(1 for status in tier_statuses if status.is_unlocked)

            section_layout.addWidget(
                TierSectionHeader(tier_key, unlocked_in_tier, len(tier_statuses))
            )

            tier_container = self._new_flow_container()
            for status in sorted(tier_statuses, key=_priority_key):
                tier_container.layout().addWidget(AchievementCard(status))
            section_layout.addWidget(tier_container)

        section_layout.addStretch()
        return container

    # --- controller-facing API ---------------------------------------------

    def set_achievements(self, statuses) -> None:
        """Store every achievement from a tuple of duck-typed
        AchievementStatus objects and render them in the current sort
        mode. Order in `statuses` itself doesn't matter -- this view
        always re-sorts locally per _sort_mode."""
        self._statuses = tuple(statuses)
        self._render()
