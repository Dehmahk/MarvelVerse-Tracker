from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin


class AchievementCriteriaType(str, enum.Enum):
    WATCH_COUNT = "watch_count"
    UNIVERSE_COMPLETE = "universe_complete"
    FRANCHISE_COMPLETE = "franchise_complete"
    GENRE_COUNT = "genre_count"
    RATING_COUNT = "rating_count"
    REWATCH_COUNT = "rewatch_count"
    COLLECTION_COMPLETE = "collection_complete"
    # A meta-achievement: percent (0-100) of every *other* achievement
    # that's unlocked. Evaluated the same way UNIVERSE_COMPLETE/
    # FRANCHISE_COMPLETE/COLLECTION_COMPLETE are (100 == unlocked), just
    # with its "total" being every other Achievement row instead of a
    # universe/franchise/collection's member projects.
    ALL_ACHIEVEMENTS_COMPLETE = "all_achievements_complete"


class AchievementTier(str, enum.Enum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    DIAMOND = "diamond"
    # The single "unlock everything else" achievement's own tier, above
    # Diamond -- deliberately not earnable any other way.
    MARVELOUS = "marvelous"


class Achievement(TimestampMixin, Base):
    """A definition of an unlockable achievement, e.g. 'Watch every Phase 1
    film' or 'Log 50 rewatches'. Criteria are evaluated by the (future)
    achievement service against watch history and user project data."""

    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tier: Mapped[AchievementTier] = mapped_column(
        Enum(AchievementTier, native_enum=False, length=16),
        default=AchievementTier.BRONZE,
        nullable=False,
    )
    criteria_type: Mapped[AchievementCriteriaType] = mapped_column(
        Enum(AchievementCriteriaType, native_enum=False, length=32), nullable=False
    )
    criteria_value: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    criteria_reference: Mapped[str | None] = mapped_column(
        String(128), nullable=True, doc="Optional slug this criteria refers to, e.g. a universe slug."
    )

    unlocks: Mapped[list["UserAchievement"]] = relationship(
        back_populates="achievement", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"<Achievement key={self.key!r}>"


class UserAchievement(Base):
    """Tracks the user's progress toward, and unlock status of, a single
    Achievement. One row per achievement, created up front at seed time."""

    __tablename__ = "user_achievements"

    id: Mapped[int] = mapped_column(primary_key=True)
    achievement_id: Mapped[int] = mapped_column(
        ForeignKey("achievements.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    progress_current: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unlocked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    achievement: Mapped["Achievement"] = relationship(back_populates="unlocks")

    @property
    def is_unlocked(self) -> bool:
        return self.unlocked_at is not None

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"<UserAchievement achievement_id={self.achievement_id} unlocked={self.is_unlocked}>"
