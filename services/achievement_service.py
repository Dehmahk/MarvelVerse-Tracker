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
from datetime import datetime, timedelta, timezone

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
    WatchHistoryEntry,
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
        AchievementCriteriaType.HIDDEN_SPECIAL,
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
    is_hidden: bool = False

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


def _hidden_perfect_order(session) -> bool:
    """Watch every Phase One MCU film, each one's *first* watch coming
    later than the previous film's first watch, in the same order the
    films actually released -- i.e. actually watched it in Phase One's
    real release order, not just watched all six eventually."""
    phase_one = session.scalars(
        select(Project).where(Project.phase == "Phase One", Project.release_date.is_not(None))
        .order_by(Project.release_date.asc())
    ).all()
    if len(phase_one) < 2:
        return False

    first_watches: list[datetime] = []
    for project in phase_one:
        earliest = session.scalar(
            select(func.min(WatchHistoryEntry.watched_at)).where(
                WatchHistoryEntry.project_id == project.id
            )
        )
        if earliest is None:
            return False
        first_watches.append(earliest)

    return all(first_watches[i] < first_watches[i + 1] for i in range(len(first_watches) - 1))


def _hidden_deja_vu(session) -> bool:
    """Rewatched the same single project 10 or more times."""
    max_rewatches = session.scalar(select(func.max(UserProjectData.rewatch_count)))
    return (max_rewatches or 0) >= 10


def _hidden_right_on_time(session) -> bool:
    """Watched something on the exact calendar anniversary (month and
    day, in a later year) of its own release date -- not just "sometime
    after release," the actual day it came out, years later."""
    rows = session.execute(
        select(WatchHistoryEntry.watched_at, Project.release_date)
        .join(Project, WatchHistoryEntry.project_id == Project.id)
        .where(Project.release_date.is_not(None))
    ).all()
    for watched_at, release_date in rows:
        if (
            watched_at.month == release_date.month
            and watched_at.day == release_date.day
            and watched_at.year > release_date.year
        ):
            return True
    return False


def _hidden_triple_feature(session) -> bool:
    """3 or more distinct projects watched on the same calendar day."""
    rows = session.execute(
        select(func.date(WatchHistoryEntry.watched_at), func.count(func.distinct(WatchHistoryEntry.project_id)))
        .group_by(func.date(WatchHistoryEntry.watched_at))
    ).all()
    return any(count >= 3 for _day, count in rows)


def _hidden_quiet_completionist(session) -> bool:
    """50+ watched projects, but not a single one of them rated --
    watching in complete, quiet volume."""
    watched_count = session.scalar(
        select(func.count()).select_from(UserProjectData).where(UserProjectData.watched.is_(True))
    )
    rating_count = session.scalar(
        select(func.count()).select_from(UserProjectData).where(UserProjectData.rating.is_not(None))
    )
    return (watched_count or 0) >= 50 and (rating_count or 0) == 0


def _hidden_social_circle(session) -> bool:
    """"Watched with" filled in on 10 or more distinct watch entries."""
    count = session.scalar(
        select(func.count()).select_from(WatchHistoryEntry).where(
            WatchHistoryEntry.watched_with.is_not(None), WatchHistoryEntry.watched_with != ""
        )
    )
    return (count or 0) >= 10


def _hidden_marathon_runner(session) -> bool:
    """Every project in some franchise with 4+ members, each one's first
    watch falling within the same 7-calendar-day window -- a genuine
    binge, not just "eventually finished the franchise.\""""
    franchises = session.scalars(select(Franchise)).all()
    for franchise in franchises:
        members = session.scalars(
            select(Project).where(Project.franchise_id == franchise.id)
        ).all()
        if len(members) < 4:
            continue

        first_watches = []
        for project in members:
            earliest = session.scalar(
                select(func.min(WatchHistoryEntry.watched_at)).where(
                    WatchHistoryEntry.project_id == project.id
                )
            )
            if earliest is None:
                break
            first_watches.append(earliest)
        else:
            if max(first_watches) - min(first_watches) <= timedelta(days=7):
                return True
    return False


def _hidden_answer_to_everything(session) -> bool:
    """A Collection containing exactly 42 projects."""
    counts = session.execute(
        select(CollectionProject.collection_id, func.count())
        .group_by(CollectionProject.collection_id)
    ).all()
    return any(count == 42 for _collection_id, count in counts)


def _hidden_renaissance_fan(session) -> bool:
    """At least one watched project from every single Universe in the
    catalog -- MCU, Fox's X-Men, SpiderVerse, and everything else, not
    just deep in one corner of it."""
    total_universes = session.scalar(select(func.count()).select_from(Universe))
    if not total_universes:
        return False
    watched_universe_count = session.scalar(
        select(func.count(func.distinct(Project.universe_id)))
        .select_from(Project)
        .join(UserProjectData, UserProjectData.project_id == Project.id)
        .where(UserProjectData.watched.is_(True), Project.universe_id.is_not(None))
    )
    return (watched_universe_count or 0) >= total_universes


def _hidden_full_circle(session) -> bool:
    """Watched both the single oldest and single newest dated release in
    the entire catalog."""
    oldest = session.scalar(
        select(Project.id).where(Project.release_date.is_not(None)).order_by(Project.release_date.asc())
    )
    newest = session.scalar(
        select(Project.id).where(Project.release_date.is_not(None)).order_by(Project.release_date.desc())
    )
    if oldest is None or newest is None or oldest == newest:
        return False
    watched_ids = {
        row[0]
        for row in session.execute(
            select(UserProjectData.project_id).where(
                UserProjectData.project_id.in_([oldest, newest]), UserProjectData.watched.is_(True)
            )
        )
    }
    return oldest in watched_ids and newest in watched_ids


# Dispatch table for HIDDEN_SPECIAL achievements -- keyed by the
# Achievement's own `key`, since these are bespoke one-off checks rather
# than a generic, parameterized criteria type.
_HIDDEN_ACHIEVEMENT_CHECKS = {
    "hidden_perfect_order": _hidden_perfect_order,
    "hidden_deja_vu": _hidden_deja_vu,
    "hidden_right_on_time": _hidden_right_on_time,
    "hidden_triple_feature": _hidden_triple_feature,
    "hidden_quiet_completionist": _hidden_quiet_completionist,
    "hidden_social_circle": _hidden_social_circle,
    "hidden_marathon_runner": _hidden_marathon_runner,
    "hidden_answer_to_everything": _hidden_answer_to_everything,
    "hidden_renaissance_fan": _hidden_renaissance_fan,
    "hidden_full_circle": _hidden_full_circle,
}


def _evaluate_hidden_special(session, achievement_key: str) -> int:
    """100 if the named hidden achievement's bespoke condition is met,
    0 otherwise -- an unrecognized key (shouldn't happen with real seed
    data) logs a warning and is treated as not-yet-met rather than
    raising, same defensive posture as an unhandled criteria_type."""
    check = _HIDDEN_ACHIEVEMENT_CHECKS.get(achievement_key)
    if check is None:
        logger.warning("No hidden-achievement check registered for key=%s", achievement_key)
        return 0
    return 100 if check(session) else 0


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
            elif criteria_type == AchievementCriteriaType.HIDDEN_SPECIAL:
                progress = _evaluate_hidden_special(session, achievement.key)
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

            is_locked_and_hidden = achievement.is_hidden and row.unlocked_at is None
            statuses.append(
                AchievementStatus(
                    key=achievement.key,
                    name="???" if is_locked_and_hidden else achievement.name,
                    description=(
                        "A hidden achievement -- keep playing to discover how to unlock it."
                        if is_locked_and_hidden
                        else achievement.description
                    ),
                    icon="mystery" if is_locked_and_hidden else achievement.icon,
                    tier=achievement.tier,
                    criteria_type=criteria_type,
                    criteria_value=achievement.criteria_value,
                    progress_current=row.progress_current,
                    unlocked_at=row.unlocked_at,
                    is_hidden=achievement.is_hidden,
                )
            )

    statuses.sort(key=_sort_key)

    if newly_unlocked:
        logger.info("Newly unlocked achievements: %s", ", ".join(newly_unlocked))

    return tuple(statuses), tuple(newly_unlocked)
