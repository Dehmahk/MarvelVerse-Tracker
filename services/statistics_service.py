from __future__ import annotations

import logging
from calendar import month_abbr
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import joinedload

from database import session_scope
from models import (
    Achievement,
    Genre,
    Project,
    ProjectStatus,
    ProjectType,
    Universe,
    UserAchievement,
    UserProjectData,
    WatchHistoryEntry,
)

logger = logging.getLogger(__name__)

# Canonical display/sort order for "Progress by Phase" -- Project.phase is
# a free-text string ("Phase One", "Phase Two", ...), so a plain
# alphabetical sort would put "Phase Five" before "Phase Four" before
# "Phase One". Any phase value not in this list (shouldn't happen with
# real seeded data) sorts after all of these, alphabetically.
_PHASE_DISPLAY_ORDER = [
    "Phase One",
    "Phase Two",
    "Phase Three",
    "Phase Four",
    "Phase Five",
    "Phase Six",
]


# Milestone 6 buckets project types into two dashboard-facing groups.
# Series-shaped content (regular, special, or animated) counts as "TV";
# everything else (movies, shorts, documentaries) counts as "Movies".
# Worth revisiting with the user if Shorts/Documentaries deserve their own
# bucket later, but this keeps the dashboard's two counters exhaustive today.
_TV_PROJECT_TYPES = (ProjectType.TV_SERIES, ProjectType.TV_SPECIAL, ProjectType.ANIMATED_SERIES)

DEFAULT_RECENT_LIMIT = 5


@dataclass(frozen=True)
class LibrarySummary:
    """A lightweight snapshot of the library, cheap enough to compute on
    every startup and on-demand refresh. Used by the shell (status bar) and,
    in a later milestone, the dashboard."""

    total_projects: int
    watched_count: int
    favorite_count: int
    universe_count: int

    @property
    def completion_percent(self) -> int:
        if self.total_projects == 0:
            return 0
        return round((self.watched_count / self.total_projects) * 100)


def get_library_summary() -> LibrarySummary:
    """Compute the current library summary. Owns its own session scope so
    callers (controllers) never need to touch the database layer directly."""
    with session_scope() as session:
        total_projects = session.scalar(select(func.count()).select_from(Project)) or 0
        watched_count = (
            session.scalar(
                select(func.count())
                .select_from(UserProjectData)
                .where(UserProjectData.watched.is_(True))
            )
            or 0
        )
        favorite_count = (
            session.scalar(
                select(func.count())
                .select_from(UserProjectData)
                .where(UserProjectData.favorite.is_(True))
            )
            or 0
        )
        universe_count = session.scalar(select(func.count()).select_from(Universe)) or 0

    summary = LibrarySummary(
        total_projects=total_projects,
        watched_count=watched_count,
        favorite_count=favorite_count,
        universe_count=universe_count,
    )
    logger.debug("Library summary: %s", summary)
    return summary


# --- Milestone 6: dashboard statistics ---------------------------------------


@dataclass(frozen=True)
class RecentWatchItem:
    """A flat, detached-safe read model for one row in the dashboard's
    "Recently Watched" panel. Built from a WatchHistoryEntry joined to its
    project, so rewatches show up as their own entries (newest first).
    Also reused as-is for the "Top Rated" panel, which shares this exact
    shape (poster, type, a date, a rating) -- there just watched_at means
    "when you logged your highest-rated watch" instead of "most recent."
    """

    project_id: int
    title: str
    project_type: ProjectType
    poster_path: str | None
    watched_at: datetime
    is_rewatch: bool
    rating: float | None


@dataclass(frozen=True)
class UniverseProgress:
    """Watched/total for one universe -- powers the Dashboard's per-
    universe progress bars, which are more informative than a single
    blended completion percentage across every universe at once."""

    universe_id: int
    name: str
    color_hex: str | None
    watched_count: int
    total_count: int

    @property
    def percent_complete(self) -> int:
        if self.total_count == 0:
            return 0
        return round((self.watched_count / self.total_count) * 100)


@dataclass(frozen=True)
class PhaseProgress:
    """Watched/total for one MCU phase -- the Dashboard's "Progress by
    Phase" alternative to "Progress by Universe", same shape as
    UniverseProgress minus a color (phases don't have one)."""

    phase: str
    watched_count: int
    total_count: int

    @property
    def percent_complete(self) -> int:
        if self.total_count == 0:
            return 0
        return round((self.watched_count / self.total_count) * 100)


@dataclass(frozen=True)
class GenreCount:
    """How many watched projects fall under one genre -- powers the
    Dashboard's genre breakdown. A single project can (and often does)
    count toward more than one genre, same as the Library's own genre
    filter."""

    name: str
    watched_count: int


@dataclass(frozen=True)
class MonthlyActivity:
    """Projects watched in one calendar month -- powers the Dashboard's
    watch-activity chart. `count` includes rewatches, same as every
    other "watched" count on this page."""

    month_label: str
    count: int


@dataclass(frozen=True)
class UpcomingRelease:
    """One not-yet-released project, for the Dashboard's "Coming Soon"
    strip."""

    project_id: int
    title: str
    project_type: ProjectType
    poster_path: str | None
    release_date: date | None


@dataclass(frozen=True)
class UpNextItem:
    """The single suggested "watch this next" project -- the first
    unreleased-excluded, not-yet-watched project in chronological order.
    None (via get_dashboard_stats' up_next field) if there's no
    chronological_order data to suggest from, or nothing left unwatched."""

    project_id: int
    title: str
    project_type: ProjectType
    poster_path: str | None
    chronological_order: int | None


@dataclass(frozen=True)
class DashboardStats:
    """Everything the Dashboard page's stat cards and "Recently Watched"
    panel need, computed in one pass so the controller only has to make a
    single call on startup/refresh."""

    total_projects: int
    watched_count: int
    movies_watched: int
    tv_watched: int
    total_minutes_watched: int
    favorite_count: int
    achievements_unlocked: int
    achievements_total: int
    recently_watched: tuple[RecentWatchItem, ...]
    top_rated: tuple[RecentWatchItem, ...]
    universe_breakdown: tuple[UniverseProgress, ...]
    phase_breakdown: tuple[PhaseProgress, ...]
    genre_breakdown: tuple[GenreCount, ...]
    monthly_activity: tuple[MonthlyActivity, ...]
    upcoming_releases: tuple[UpcomingRelease, ...]
    up_next: UpNextItem | None

    @property
    def completion_percent(self) -> int:
        if self.total_projects == 0:
            return 0
        return round((self.watched_count / self.total_projects) * 100)

    @property
    def total_hours_watched(self) -> float:
        return round(self.total_minutes_watched / 60, 1)


def get_dashboard_stats(recent_limit: int = DEFAULT_RECENT_LIMIT) -> DashboardStats:
    """Compute everything the Dashboard page needs. Owns its own session
    scope, like everything else in this module -- callers get back a
    single detached DTO, never live ORM instances.

    Achievement counts are wired up against the real ``Achievement`` /
    ``UserAchievement`` tables from M2, but nothing populates or checks
    them yet (that's scoped to a later milestone), so both will legitimately
    read 0 until that lands -- this is not a hardcoded placeholder, it's an
    accurate count of an empty table.
    """
    with session_scope() as session:
        total_projects = session.scalar(select(func.count()).select_from(Project)) or 0

        watched_count = (
            session.scalar(
                select(func.count())
                .select_from(UserProjectData)
                .where(UserProjectData.watched.is_(True))
            )
            or 0
        )
        favorite_count = (
            session.scalar(
                select(func.count())
                .select_from(UserProjectData)
                .where(UserProjectData.favorite.is_(True))
            )
            or 0
        )

        movies_watched = (
            session.scalar(
                select(func.count())
                .select_from(Project)
                .join(UserProjectData, UserProjectData.project_id == Project.id)
                .where(
                    UserProjectData.watched.is_(True),
                    Project.project_type.not_in(_TV_PROJECT_TYPES),
                )
            )
            or 0
        )
        tv_watched = (
            session.scalar(
                select(func.count())
                .select_from(Project)
                .join(UserProjectData, UserProjectData.project_id == Project.id)
                .where(
                    UserProjectData.watched.is_(True),
                    Project.project_type.in_(_TV_PROJECT_TYPES),
                )
            )
            or 0
        )
        total_minutes_watched = (
            session.scalar(
                select(func.coalesce(func.sum(Project.runtime_minutes), 0))
                .select_from(Project)
                .join(UserProjectData, UserProjectData.project_id == Project.id)
                .where(UserProjectData.watched.is_(True))
            )
            or 0
        )

        achievements_total = session.scalar(select(func.count()).select_from(Achievement)) or 0
        achievements_unlocked = (
            session.scalar(
                select(func.count())
                .select_from(UserAchievement)
                .where(UserAchievement.unlocked_at.is_not(None))
            )
            or 0
        )

        recent_stmt = (
            select(WatchHistoryEntry)
            .join(Project, WatchHistoryEntry.project_id == Project.id)
            .options(joinedload(WatchHistoryEntry.project).joinedload(Project.user_data))
            # Same tiebreak as Project.watch_history's ordering: SQLite's
            # CURRENT_TIMESTAMP is only second-precision, so ties fall back
            # to insertion order via id.
            .order_by(WatchHistoryEntry.watched_at.desc(), WatchHistoryEntry.id.desc())
            .limit(recent_limit)
        )
        entries = session.scalars(recent_stmt).unique().all()
        recently_watched = tuple(
            RecentWatchItem(
                project_id=entry.project_id,
                title=entry.project.title,
                project_type=entry.project.project_type,
                poster_path=entry.project.poster_path,
                watched_at=entry.watched_at,
                is_rewatch=entry.is_rewatch,
                rating=entry.project.user_data.rating if entry.project.user_data else None,
            )
            for entry in entries
        )

        # Top Rated: watched projects with a rating, highest first. Uses
        # each project's most recent watch (or first watch, if it's never
        # been logged via log_watch()) purely for a "watched_at" value to
        # satisfy RecentWatchItem's shape -- the sort itself is by rating,
        # not by that date.
        top_rated_stmt = (
            select(Project, UserProjectData)
            .join(UserProjectData, UserProjectData.project_id == Project.id)
            .where(UserProjectData.rating.is_not(None))
            .order_by(UserProjectData.rating.desc(), Project.title.asc())
            .limit(recent_limit)
        )
        top_rated = tuple(
            RecentWatchItem(
                project_id=project.id,
                title=project.title,
                project_type=project.project_type,
                poster_path=project.poster_path,
                watched_at=(
                    datetime.combine(user_data.last_watched_date, datetime.min.time())
                    if user_data.last_watched_date is not None
                    else project.updated_at
                ),
                is_rewatch=False,
                rating=user_data.rating,
            )
            for project, user_data in session.execute(top_rated_stmt).all()
        )

        # Per-universe progress: only universes that actually have any
        # projects at all -- an empty universe (or a typo'd future one)
        # would otherwise show a meaningless "0 / 0" bar.
        universe_rows = session.execute(
            select(
                Universe.id,
                Universe.name,
                Universe.color_hex,
                func.count(Project.id).label("total"),
                func.sum(case((UserProjectData.watched.is_(True), 1), else_=0)).label("watched"),
            )
            .select_from(Universe)
            .join(Project, Project.universe_id == Universe.id)
            .outerjoin(UserProjectData, UserProjectData.project_id == Project.id)
            .group_by(Universe.id)
            .having(func.count(Project.id) > 0)
            .order_by(Universe.sort_order)
        ).all()
        universe_breakdown = tuple(
            UniverseProgress(
                universe_id=row.id,
                name=row.name,
                color_hex=row.color_hex,
                watched_count=row.watched or 0,
                total_count=row.total,
            )
            for row in universe_rows
        )

        # Phase breakdown: only phases that actually have any projects --
        # same "don't show a meaningless 0/0" rule as universe_breakdown.
        # Project.phase is NULL for a lot of the catalog (documentaries,
        # specials, non-MCU universes), so those are excluded entirely
        # rather than lumped into a meaningless "no phase" bucket.
        phase_rows = session.execute(
            select(
                Project.phase,
                func.count(Project.id).label("total"),
                func.sum(case((UserProjectData.watched.is_(True), 1), else_=0)).label("watched"),
            )
            .select_from(Project)
            .outerjoin(UserProjectData, UserProjectData.project_id == Project.id)
            .where(Project.phase.is_not(None))
            .group_by(Project.phase)
        ).all()
        phase_breakdown = tuple(
            sorted(
                (
                    PhaseProgress(phase=row.phase, watched_count=row.watched or 0, total_count=row.total)
                    for row in phase_rows
                ),
                key=lambda p: (
                    _PHASE_DISPLAY_ORDER.index(p.phase) if p.phase in _PHASE_DISPLAY_ORDER else len(_PHASE_DISPLAY_ORDER),
                    p.phase,
                ),
            )
        )

        # Genre breakdown: top genres by watched count (not total count --
        # this is "what you actually watch", not "what's in the catalog").
        genre_rows = session.execute(
            select(Genre.name, func.count(Project.id).label("watched"))
            .select_from(Genre)
            .join(Genre.projects)
            .join(UserProjectData, UserProjectData.project_id == Project.id)
            .where(UserProjectData.watched.is_(True))
            .group_by(Genre.id)
            .order_by(func.count(Project.id).desc(), Genre.name.asc())
            .limit(5)
        ).all()
        genre_breakdown = tuple(GenreCount(name=row.name, watched_count=row.watched) for row in genre_rows)

        # Monthly activity: the last 6 calendar months (this one included),
        # zero-filled so a quiet month still renders a (empty) bar instead
        # of just vanishing from the chart.
        monthly_counts: dict[tuple[int, int], int] = {}
        for entry in session.scalars(
            select(WatchHistoryEntry).where(
                WatchHistoryEntry.watched_at >= _months_ago(datetime.now(), 5).replace(day=1)
            )
        ):
            key = (entry.watched_at.year, entry.watched_at.month)
            monthly_counts[key] = monthly_counts.get(key, 0) + 1

        now = datetime.now()
        monthly_activity = tuple(
            MonthlyActivity(
                month_label=f"{month_abbr[month]}",
                count=monthly_counts.get((year, month), 0),
            )
            for year, month in (_year_month(_months_ago(now, i)) for i in range(5, -1, -1))
        )

        # Upcoming releases: not-yet-released projects, soonest first.
        # Undated announced projects (release_date is None) sort last
        # rather than first, since "TBA" isn't "soonest."
        upcoming_stmt = (
            select(Project)
            .where(
                Project.status.in_(
                    (ProjectStatus.UPCOMING, ProjectStatus.ANNOUNCED, ProjectStatus.IN_PRODUCTION)
                ),
                (Project.release_date.is_(None)) | (Project.release_date >= date.today()),
            )
            .order_by(Project.release_date.is_(None), Project.release_date.asc())
            .limit(recent_limit)
        )
        upcoming_releases = tuple(
            UpcomingRelease(
                project_id=project.id,
                title=project.title,
                project_type=project.project_type,
                poster_path=project.poster_path,
                release_date=project.release_date,
            )
            for project in session.scalars(upcoming_stmt).all()
        )

        # Up Next: the first not-yet-watched, not-skipped RELEASED project
        # in chronological order -- suggesting an unreleased project would
        # be useless, and chronological_order is NULL for a lot of the
        # catalog (documentaries, specials, ...) so those are excluded
        # too, same as Timeline's Chronological sort already excludes
        # them by saga. Skipped projects are excluded for the same reason
        # watched ones are: recommending something the user has already
        # deliberately passed on isn't useful.
        up_next_row = session.scalar(
            select(Project)
            .outerjoin(UserProjectData, UserProjectData.project_id == Project.id)
            .where(
                Project.status == ProjectStatus.RELEASED,
                Project.chronological_order.is_not(None),
                UserProjectData.watched.is_not(True),
                UserProjectData.skipped.is_not(True),
            )
            .order_by(Project.chronological_order.asc())
            .limit(1)
        )
        up_next = (
            UpNextItem(
                project_id=up_next_row.id,
                title=up_next_row.title,
                project_type=up_next_row.project_type,
                poster_path=up_next_row.poster_path,
                chronological_order=up_next_row.chronological_order,
            )
            if up_next_row is not None
            else None
        )

    stats = DashboardStats(
        total_projects=total_projects,
        watched_count=watched_count,
        movies_watched=movies_watched,
        tv_watched=tv_watched,
        total_minutes_watched=total_minutes_watched,
        favorite_count=favorite_count,
        achievements_unlocked=achievements_unlocked,
        achievements_total=achievements_total,
        recently_watched=recently_watched,
        top_rated=top_rated,
        universe_breakdown=universe_breakdown,
        phase_breakdown=phase_breakdown,
        genre_breakdown=genre_breakdown,
        monthly_activity=monthly_activity,
        upcoming_releases=upcoming_releases,
        up_next=up_next,
    )
    logger.debug("Dashboard stats: %s", stats)
    return stats


def _months_ago(when: datetime, n: int) -> datetime:
    """`when` shifted back by `n` whole calendar months (day-of-month
    preserved where possible, clamped for shorter months) -- used to
    build the last-6-months window for monthly_activity without pulling
    in a date-arithmetic dependency for just this."""
    month_index = when.month - 1 - n
    year = when.year + month_index // 12
    month = month_index % 12 + 1
    return when.replace(year=year, month=month, day=1)


def _year_month(when: datetime) -> tuple[int, int]:
    return (when.year, when.month)
