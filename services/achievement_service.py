"""Milestone 9: achievement tracking.

``sync_achievements()`` is the single entry point. It recomputes
``progress_current`` for every seeded :class:`~models.Achievement` row in
one session, based on the current state of ``UserProjectData`` /
``Project``, and unlocks anything that has newly crossed its threshold.
It's cheap enough to call after every user action that could move the
needle -- logging a watch, editing a rating, a TMDB sync bringing in new
projects -- rather than trying to incrementally patch individual counters
from half a dozen different call sites.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import joinedload

from database import session_scope
from models import (
    Achievement,
    AchievementCriteriaType,
    AchievementTier,
    Collection,
    CollectionProject,
    Franchise,
    Project,
    Universe,
    UserAchievement,
    UserProjectData,
)

logger = logging.getLogger(__name__)

# Criteria types this module doesn't yet know how to evaluate: GENRE_COUNT's
# exact semantics (watched count within one named genre? distinct genres
# watched at all?) haven't been decided with the user. Progress for these
# is simply left exactly as it was on the previous sync -- never guessed
# at, never silently unlocked, never regressed -- until a future milestone
# defines them for real.
_UNSUPPORTED_CRITERIA = frozenset({AchievementCriteriaType.GENRE_COUNT})

# For UNIVERSE_COMPLETE/FRANCHISE_COMPLETE/COLLECTION_COMPLETE, criteria_value
# is a boolean-ish marker (always 1 in the seed data) meaning "must be 100%
# complete", not a percentage threshold to compare progress against
# directly -- so these criteria types are unlocked on progress reaching 100
# (%), never on progress >= criteria_value the way every count-based
# criteria type is.
_COMPLETION_CRITERIA = frozenset(
    {
        AchievementCriteriaType.UNIVERSE_COMPLETE,
        AchievementCriteriaType.FRANCHISE_COMPLETE,
        AchievementCriteriaType.COLLECTION_COMPLETE,
        AchievementCriteriaType.ALL_ACHIEVEMENTS_COMPLETE,
    }
)

_TIER_ORDER = {
    AchievementTier.BRONZE: 0,
    AchievementTier.SILVER: 1,
    AchievementTier.GOLD: 2,
    AchievementTier.PLATINUM: 3,
    AchievementTier.DIAMOND: 4,
    AchievementTier.MARVELOUS: 5,
}


@dataclass(frozen=True)
class AchievementStatus:
    """A flat, detached-safe read model combining one achievement's static
    definition with the user's live progress toward it."""

    key: str
    name: str
    description: str | None
    icon: str | None
    tier: AchievementTier
    criteria_type: AchievementCriteriaType
    criteria_value: int
    progress_current: int
    unlocked_at: datetime | None

    @property
    def is_unlocked(self) -> bool:
        return self.unlocked_at is not None

    @property
    def percent_complete(self) -> int:
        if self.criteria_type in _COMPLETION_CRITERIA:
            return max(0, min(100, self.progress_current))
        if self.criteria_value <= 0:
            return 100 if self.is_unlocked else 0
        return max(0, min(100, round((self.progress_current / self.criteria_value) * 100)))

    @property
    def progress_label(self) -> str:
        """A short, criteria-appropriate string for the progress bar
        caption -- e.g. "3 / 25" for a count-based achievement, or
        "62% complete" for a universe/franchise completion one."""
        if self.criteria_type in _COMPLETION_CRITERIA:
            return f"{self.percent_complete}% complete"
        return f"{min(self.progress_current, self.criteria_value)} / {self.criteria_value}"


def _watched_count(session) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(UserProjectData)
            .where(UserProjectData.watched.is_(True))
        )
        or 0
    )


def _rewatch_total(session) -> int:
    return session.scalar(select(func.coalesce(func.sum(UserProjectData.rewatch_count), 0))) or 0


def _rating_count(session) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(UserProjectData)
            .where(UserProjectData.rating.is_not(None))
        )
        or 0
    )


def _universe_completion_percents(session) -> dict[str, int]:
    """Percent (0-100) of every universe's projects that are watched, in
    a single grouped query, keyed by slug -- computed once per
    sync_achievements() call and looked up per-achievement below, rather
    than a dedicated pair of queries for every single achievement that
    happens to reference a universe (there were 3 of those at last
    count, each doing its own "find the id, then two separate COUNT
    queries" round trip -- this collapses all of that into one query,
    regardless of how many achievements end up referencing universes as
    the seeded list grows). A universe with no projects at all is
    naturally absent from these results; callers should treat a missing
    key the same as 0%, same as the old per-slug version did for an
    empty/unrecognized slug."""
    rows = session.execute(
        select(
            Universe.slug,
            func.count(Project.id).label("total"),
            func.sum(case((UserProjectData.watched.is_(True), 1), else_=0)).label("watched"),
        )
        .select_from(Universe)
        .join(Project, Project.universe_id == Universe.id)
        .outerjoin(UserProjectData, UserProjectData.project_id == Project.id)
        .group_by(Universe.slug)
    ).all()
    return {row.slug: round(((row.watched or 0) / row.total) * 100) for row in rows if row.total}


def _franchise_completion_percents(session) -> dict[str, int]:
    """Same as :func:`_universe_completion_percents`, scoped to
    franchises."""
    rows = session.execute(
        select(
            Franchise.slug,
            func.count(Project.id).label("total"),
            func.sum(case((UserProjectData.watched.is_(True), 1), else_=0)).label("watched"),
        )
        .select_from(Franchise)
        .join(Project, Project.franchise_id == Franchise.id)
        .outerjoin(UserProjectData, UserProjectData.project_id == Project.id)
        .group_by(Franchise.slug)
    ).all()
    return {row.slug: round(((row.watched or 0) / row.total) * 100) for row in rows if row.total}


def _collection_completion_percents(session) -> dict[str, int]:
    """Same as :func:`_universe_completion_percents`, scoped to
    user-curated collections."""
    rows = session.execute(
        select(
            Collection.slug,
            func.count(CollectionProject.project_id).label("total"),
            func.sum(case((UserProjectData.watched.is_(True), 1), else_=0)).label("watched"),
        )
        .select_from(Collection)
        .join(CollectionProject, CollectionProject.collection_id == Collection.id)
        .outerjoin(UserProjectData, UserProjectData.project_id == CollectionProject.project_id)
        .group_by(Collection.slug)
    ).all()
    return {row.slug: round(((row.watched or 0) / row.total) * 100) for row in rows if row.total}


def _all_achievements_percent(session, self_id: int) -> int:
    """Percent (0-100) of every *other* achievement (i.e. excluding
    `self_id` -- the ALL_ACHIEVEMENTS_COMPLETE achievement itself, which
    would otherwise need to unlock itself to unlock itself) that's
    currently unlocked. There's no criteria_reference to key off here
    (unlike universe/franchise/collection), since there's only ever
    meant to be one such achievement -- excluding by id is simpler and
    doesn't depend on that staying true."""
    total = session.scalar(select(func.count()).select_from(Achievement).where(Achievement.id != self_id)) or 0
    if total == 0:
        return 0
    unlocked = (
        session.scalar(
            select(func.count())
            .select_from(UserAchievement)
            .where(UserAchievement.achievement_id != self_id, UserAchievement.unlocked_at.is_not(None))
        )
        or 0
    )
    return round((unlocked / total) * 100)


def _sort_key(status: AchievementStatus) -> tuple:
    # Unlocked achievements first (most recently unlocked at the top, as
    # a small celebration), then locked ones ordered by how close they
    # are to unlocking (so the next achievable one is always visible up
    # top), tier, then key as a final deterministic tiebreak.
    if status.is_unlocked:
        return (0, -status.unlocked_at.timestamp())
    return (1, -status.percent_complete, _TIER_ORDER.get(status.tier, 99), status.key)


def sync_achievements() -> tuple[tuple[AchievementStatus, ...], tuple[str, ...]]:
    """Recompute progress for every achievement and unlock any that have
    newly crossed their threshold, in one session.

    Never re-locks an already-unlocked achievement even if progress
    (impossibly) regresses -- ``unlocked_at`` is a permanent record of a
    real, past accomplishment, not a live gauge that can flicker off.

    Returns ``(all_statuses, newly_unlocked_names)``. The second element
    is empty on a routine refresh with nothing new to report, and
    non-empty only on the call that actually pushed an achievement over
    its threshold, so callers can show a "just unlocked" notification
    exactly once rather than re-showing it on every subsequent refresh.
    """
    newly_unlocked: list[str] = []
    statuses: list[AchievementStatus] = []

    with session_scope() as session:
        watched_count = _watched_count(session)
        rewatch_total = _rewatch_total(session)
        rating_count = _rating_count(session)
        universe_percents = _universe_completion_percents(session)
        franchise_percents = _franchise_completion_percents(session)
        collection_percents = _collection_completion_percents(session)

        rows = session.scalars(
            select(UserAchievement).options(joinedload(UserAchievement.achievement))
        ).all()

        for row in rows:
            achievement = row.achievement
            criteria_type = achievement.criteria_type

            if criteria_type == AchievementCriteriaType.WATCH_COUNT:
                progress = watched_count
            elif criteria_type == AchievementCriteriaType.REWATCH_COUNT:
                progress = rewatch_total
            elif criteria_type == AchievementCriteriaType.RATING_COUNT:
                progress = rating_count
            elif criteria_type == AchievementCriteriaType.UNIVERSE_COMPLETE:
                progress = universe_percents.get(achievement.criteria_reference or "", 0)
            elif criteria_type == AchievementCriteriaType.FRANCHISE_COMPLETE:
                progress = franchise_percents.get(achievement.criteria_reference or "", 0)
            elif criteria_type == AchievementCriteriaType.COLLECTION_COMPLETE:
                progress = collection_percents.get(achievement.criteria_reference or "", 0)
            elif criteria_type == AchievementCriteriaType.ALL_ACHIEVEMENTS_COMPLETE:
                progress = _all_achievements_percent(session, achievement.id)
            elif criteria_type in _UNSUPPORTED_CRITERIA:
                progress = row.progress_current
            else:  # pragma: no cover - defensive; every real enum value is handled above
                logger.warning(
                    "Unhandled achievement criteria_type=%s for key=%s -- progress left unchanged",
                    criteria_type,
                    achievement.key,
                )
                progress = row.progress_current

            row.progress_current = progress

            if row.unlocked_at is None:
                threshold_met = (
                    progress >= 100
                    if criteria_type in _COMPLETION_CRITERIA
                    else progress >= achievement.criteria_value
                )
                if threshold_met:
                    # A naive UTC datetime, matching every other timestamp
                    # column in this schema (TimestampMixin's created_at/
                    # updated_at are populated by SQLite's CURRENT_TIMESTAMP,
                    # which is also naive UTC) -- datetime.utcnow() would do
                    # the same thing but is deprecated as of Python 3.12.
                    row.unlocked_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    newly_unlocked.append(achievement.name)

            statuses.append(
                AchievementStatus(
                    key=achievement.key,
                    name=achievement.name,
                    description=achievement.description,
                    icon=achievement.icon,
                    tier=achievement.tier,
                    criteria_type=criteria_type,
                    criteria_value=achievement.criteria_value,
                    progress_current=row.progress_current,
                    unlocked_at=row.unlocked_at,
                )
            )

    statuses.sort(key=_sort_key)

    if newly_unlocked:
        logger.info("Newly unlocked achievements: %s", ", ".join(newly_unlocked))

    return tuple(statuses), tuple(newly_unlocked)
