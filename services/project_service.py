from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from database import session_scope
from models import (
    Franchise,
    Genre,
    Person,
    Project,
    ProjectCast,
    ProjectCrew,
    ProjectStatus,
    ProjectType,
    Universe,
    UserProjectData,
    WatchHistoryEntry,
)

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 24


class SortField(str, Enum):
    TITLE = "title"
    RELEASE_DATE = "release_date"
    RATING = "rating"
    CHRONOLOGICAL_ORDER = "chronological_order"
    RECENTLY_ADDED = "recently_added"


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


# A curated list, not every name ever credited -- character_name is free
# text in real cast data (often compound: "Steve Rogers / Captain America
# (voice)"), so there's no clean way to derive a full, deduplicated
# character list straight from the database. This covers the well-known
# headline characters across every universe currently in the catalog;
# ProjectFilter.character_name substring-matches against whichever of
# these is picked, so it still catches a character however their
# specific credit happens to be worded.
CHARACTER_FILTER_OPTIONS: tuple[str, ...] = (
    "Iron Man",
    "Captain America",
    "Thor",
    "Hulk",
    "Black Widow",
    "Hawkeye",
    "Nick Fury",
    "Loki",
    "Scarlet Witch",
    "Vision",
    "Ant-Man",
    "Wasp",
    "Doctor Strange",
    "Black Panther",
    "Captain Marvel",
    "Star-Lord",
    "Gamora",
    "Rocket",
    "Groot",
    "Drax",
    "Spider-Man",
    "Venom",
    "Morbius",
    "Wolverine",
    "Deadpool",
    "Professor X",
    "Magneto",
    "Mystique",
    "Cyclops",
    "Storm",
    "Jean Grey",
    "Ghost Rider",
    "Blade",
    "Daredevil",
    "The Punisher",
    "Jessica Jones",
    "Luke Cage",
    "Iron Fist",
    "Elektra",
    "Nova",
    "She-Hulk",
    "Ms. Marvel",
    "Moon Knight",
    "Shang-Chi",
    "Eternals",
)


@dataclass(frozen=True)
class ProjectFilter:
    """All the criteria the Library view can narrow the project list by.

    Every field is optional; ``None`` means "don't filter on this". This is
    a plain, hashable value object so the controller/view layer can build
    and compare filter state without touching the database or services
    beyond calling :func:`list_projects`.
    """

    search_text: str | None = None
    universe_id: int | None = None
    franchise_id: int | None = None
    genre_id: int | None = None
    project_type: ProjectType | None = None
    status: ProjectStatus | None = None
    watched: bool | None = None
    favorite: bool | None = None
    wishlist: bool | None = None
    skipped: bool | None = None
    # Substring-matched (case-insensitive) against ProjectCast.character_name,
    # not an exact match -- real cast credits are free text and often
    # compound ("Steve Rogers / Captain America (voice)", "Hulk / Edwin
    # Jarvis / Additional Voices (voice)"), so an exact-match filter would
    # miss most of them. See CHARACTER_FILTER_OPTIONS for the curated list
    # of names the Library's Character filter actually offers.
    character_name: str | None = None
    # When True, only RELEASED projects are returned -- driven by the
    # Settings > Library "Show upcoming/announced projects" toggle, not
    # exposed as its own Library filter-row control. Deliberately excluded
    # from is_active()'s "any narrowing criteria set" check below: it's a
    # standing preference the user has already dismissed as a settings
    # decision, not an active filter they'd expect a "Clear Filters"
    # affordance to reset.
    exclude_unreleased: bool = False

    def is_active(self) -> bool:
        """Whether any narrowing criteria is set (used by the UI to show
        an "active filters" indicator / a clear-filters affordance)."""
        return any(
            value is not None
            for field_name, value in vars(self).items()
            if field_name not in ("search_text", "exclude_unreleased")
        ) or bool(self.search_text and self.search_text.strip())


@dataclass(frozen=True)
class ProjectListItem:
    """A flat, detached-safe read model for one row in the library.

    Built entirely inside the owning session_scope so callers (views,
    controllers) never touch a lazy-loaded ORM instance after the session
    that produced it has closed.
    """

    id: int
    title: str
    slug: str
    project_type: ProjectType
    status: ProjectStatus
    release_date: date | None
    runtime_minutes: int | None
    studio: str | None
    poster_path: str | None
    universe_name: str | None
    franchise_name: str | None
    genre_names: tuple[str, ...]
    watched: bool
    favorite: bool
    wishlist: bool
    skipped: bool
    rating: float | None


@dataclass(frozen=True)
class PagedResult:
    """One page of :class:`ProjectListItem` rows plus enough bookkeeping
    for the Library view to render pagination controls without doing any
    of its own arithmetic (or touching the database)."""

    items: list[ProjectListItem]
    total_count: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        if self.total_count == 0:
            return 1
        return math.ceil(self.total_count / self.page_size)

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_previous(self) -> bool:
        return self.page > 1


@dataclass(frozen=True)
class FilterOptions:
    """Reference data for populating the Library's filter dropdowns.
    ``franchises`` entries are ``(id, name, universe_id)`` so the UI can
    narrow the franchise list down to whichever universe is selected.
    """

    universes: list[tuple[int, str]]
    franchises: list[tuple[int, str, int]]
    genres: list[tuple[int, str]]


def _apply_filters(stmt, filters: ProjectFilter):
    if filters.universe_id is not None:
        stmt = stmt.where(Project.universe_id == filters.universe_id)
    if filters.franchise_id is not None:
        stmt = stmt.where(Project.franchise_id == filters.franchise_id)
    if filters.project_type is not None:
        stmt = stmt.where(Project.project_type == filters.project_type)
    if filters.status is not None:
        stmt = stmt.where(Project.status == filters.status)
    if filters.genre_id is not None:
        stmt = stmt.where(Project.genres.any(Genre.id == filters.genre_id))
    if filters.watched is not None:
        stmt = stmt.where(UserProjectData.watched.is_(filters.watched))
    if filters.favorite is not None:
        stmt = stmt.where(UserProjectData.favorite.is_(filters.favorite))
    if filters.wishlist is not None:
        stmt = stmt.where(UserProjectData.wishlist.is_(filters.wishlist))
    if filters.skipped is not None:
        stmt = stmt.where(UserProjectData.skipped.is_(filters.skipped))
    if filters.character_name:
        needle = f"%{filters.character_name}%"
        stmt = stmt.where(Project.cast.any(ProjectCast.character_name.ilike(needle)))
    if filters.exclude_unreleased and filters.status is None:
        # Only applies when the user hasn't picked an explicit Status
        # filter of their own -- an interactive "show me Upcoming" choice
        # should always win over this standing default, not silently
        # collide with it into an always-empty result.
        stmt = stmt.where(Project.status == ProjectStatus.RELEASED)

    search_text = (filters.search_text or "").strip()
    if search_text:
        needle = f"%{search_text}%"
        cast_match = Project.cast.any(ProjectCast.person.has(Person.name.ilike(needle)))
        crew_match = Project.crew.any(ProjectCrew.person.has(Person.name.ilike(needle)))
        stmt = stmt.where(
            or_(
                Project.title.ilike(needle),
                Project.synopsis.ilike(needle),
                Project.studio.ilike(needle),
                Project.universe.has(Universe.name.ilike(needle)),
                Project.franchise.has(Franchise.name.ilike(needle)),
                cast_match,
                crew_match,
            )
        )
    return stmt


_SORT_COLUMNS = {
    SortField.TITLE: Project.title,
    SortField.RELEASE_DATE: Project.release_date,
    SortField.CHRONOLOGICAL_ORDER: Project.chronological_order,
    SortField.RECENTLY_ADDED: Project.created_at,
}


def _apply_sort(stmt, sort_field: SortField, sort_direction: SortDirection):
    column = UserProjectData.rating if sort_field == SortField.RATING else _SORT_COLUMNS[sort_field]
    ordered = column.desc().nulls_last() if sort_direction == SortDirection.DESC else column.asc().nulls_last()
    # Stable secondary sort by title so ties (and NULLs) render deterministically.
    return stmt.order_by(ordered, Project.title.asc())


def list_projects(
    filters: ProjectFilter | None = None,
    sort_field: SortField = SortField.TITLE,
    sort_direction: SortDirection = SortDirection.ASC,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> PagedResult:
    """Search, filter, sort, and paginate the project library.

    Owns its own session scope — callers always get back plain, detached
    :class:`ProjectListItem` rows, never live ORM instances, so this is
    safe to call from a controller without leaking session lifetime into
    the view layer.
    """
    filters = filters or ProjectFilter()
    page = max(1, page)
    page_size = max(1, page_size)

    with session_scope() as session:
        id_stmt = _apply_filters(
            select(Project.id).outerjoin(
                UserProjectData, UserProjectData.project_id == Project.id
            ),
            filters,
        ).distinct()

        total_count = session.scalar(
            select(func.count()).select_from(id_stmt.subquery())
        ) or 0

        page_stmt = _apply_sort(
            _apply_filters(
                select(Project).outerjoin(
                    UserProjectData, UserProjectData.project_id == Project.id
                ),
                filters,
            ).distinct(),
            sort_field,
            sort_direction,
        )
        page_stmt = page_stmt.options(
            joinedload(Project.universe),
            joinedload(Project.franchise),
            joinedload(Project.user_data),
            selectinload(Project.genres),
        )
        page_stmt = page_stmt.offset((page - 1) * page_size).limit(page_size)

        projects = session.scalars(page_stmt).unique().all()

        items = [
            ProjectListItem(
                id=p.id,
                title=p.title,
                slug=p.slug,
                project_type=p.project_type,
                status=p.status,
                release_date=p.release_date,
                runtime_minutes=p.runtime_minutes,
                studio=p.studio,
                poster_path=p.poster_path,
                universe_name=p.universe.name if p.universe else None,
                franchise_name=p.franchise.name if p.franchise else None,
                genre_names=tuple(g.name for g in p.genres),
                watched=p.user_data.watched if p.user_data else False,
                favorite=p.user_data.favorite if p.user_data else False,
                wishlist=p.user_data.wishlist if p.user_data else False,
                skipped=p.user_data.skipped if p.user_data else False,
                rating=p.user_data.rating if p.user_data else None,
            )
            for p in projects
        ]

    result = PagedResult(items=items, total_count=total_count, page=page, page_size=page_size)
    logger.debug(
        "list_projects: %d/%d results (page %d/%d, sort=%s %s)",
        len(items),
        total_count,
        page,
        result.total_pages,
        sort_field.value,
        sort_direction.value,
    )
    return result


def get_filter_options() -> FilterOptions:
    """Reference data (universes, franchises, genres) for populating the
    Library view's filter controls. Cheap enough to call every time the
    filter panel opens; owns its own session scope like everything else
    in this module."""
    with session_scope() as session:
        universes = [
            (u.id, u.name)
            for u in session.scalars(select(Universe).order_by(Universe.sort_order)).all()
        ]
        franchises = [
            (f.id, f.name, f.universe_id)
            for f in session.scalars(select(Franchise).order_by(Franchise.name)).all()
        ]
        genres = [
            (g.id, g.name) for g in session.scalars(select(Genre).order_by(Genre.name)).all()
        ]
    return FilterOptions(universes=universes, franchises=franchises, genres=genres)


# --- Milestone 5: project detail --------------------------------------------


@dataclass(frozen=True)
class CastMember:
    person_id: int
    name: str
    character_name: str | None
    photo_path: str | None


@dataclass(frozen=True)
class CrewMember:
    person_id: int
    name: str
    role: str
    photo_path: str | None


@dataclass(frozen=True)
class WatchHistoryItem:
    id: int
    watched_at: datetime
    is_rewatch: bool
    notes: str | None
    watched_with: str | None


@dataclass(frozen=True)
class TimelineNeighbor:
    """A minimal read model for the project immediately before/after this
    one in chronological_order -- powers Project Details' "Previous/Next
    in the Marvel Timeline" quick-nav buttons."""

    id: int
    title: str
    chronological_order: int


@dataclass(frozen=True)
class ProjectDetail:
    """A flat, detached-safe read model for the Project Details page.

    Like :class:`ProjectListItem`, built entirely inside the owning
    session_scope so callers never touch a lazy-loaded ORM instance after
    the session that produced it has closed.
    """

    id: int
    title: str
    slug: str
    project_type: ProjectType
    status: ProjectStatus
    release_date: date | None
    in_universe_date: str | None
    season_count: int | None
    episode_count: int | None
    cancelled_date: date | None
    next_season_release_date: date | None
    production_start_date: date | None
    runtime_minutes: int | None
    studio: str | None
    synopsis: str | None
    poster_path: str | None
    background_path: str | None
    trailer_url: str | None
    saga: str | None
    phase: str | None
    chronological_order: int | None
    universe_name: str | None
    franchise_name: str | None
    genre_names: tuple[str, ...]
    cast: tuple[CastMember, ...]
    crew: tuple[CrewMember, ...]
    watched: bool
    favorite: bool
    wishlist: bool
    skipped: bool
    rating: float | None
    notes: str | None
    rewatch_count: int
    last_watched_date: date | None
    watch_history: tuple[WatchHistoryItem, ...]
    previous_in_timeline: TimelineNeighbor | None
    next_in_timeline: TimelineNeighbor | None
    tmdb_id: int | None


def get_project_detail(project_id: int) -> ProjectDetail | None:
    """Full detail read model for a single project, or ``None`` if no
    project with that id exists. Owns its own session scope."""
    with session_scope() as session:
        stmt = (
            select(Project)
            .where(Project.id == project_id)
            .options(
                joinedload(Project.universe),
                joinedload(Project.franchise),
                joinedload(Project.user_data),
                selectinload(Project.genres),
                selectinload(Project.cast).joinedload(ProjectCast.person),
                selectinload(Project.crew).joinedload(ProjectCrew.person),
                selectinload(Project.watch_history),
            )
        )
        project = session.scalars(stmt).unique().one_or_none()
        if project is None:
            return None

        cast = tuple(
            CastMember(
                person_id=c.person_id,
                name=c.person.name,
                character_name=c.character_name,
                photo_path=c.person.photo_path,
            )
            for c in project.cast
        )
        crew = tuple(
            CrewMember(
                person_id=c.person_id,
                name=c.person.name,
                role=c.role,
                photo_path=c.person.photo_path,
            )
            for c in project.crew
        )
        watch_history = tuple(
            WatchHistoryItem(
                id=w.id,
                watched_at=w.watched_at,
                is_rewatch=w.is_rewatch,
                notes=w.notes,
                watched_with=w.watched_with,
            )
            for w in project.watch_history
        )

        user_data = project.user_data
        detail = ProjectDetail(
            id=project.id,
            title=project.title,
            slug=project.slug,
            project_type=project.project_type,
            status=project.status,
            release_date=project.release_date,
            in_universe_date=project.in_universe_date,
            season_count=project.season_count,
            episode_count=project.episode_count,
            cancelled_date=project.cancelled_date,
            next_season_release_date=project.next_season_release_date,
            production_start_date=project.production_start_date,
            runtime_minutes=project.runtime_minutes,
            studio=project.studio,
            synopsis=project.synopsis,
            poster_path=project.poster_path,
            background_path=project.background_path,
            trailer_url=project.trailer_url,
            saga=project.saga,
            phase=project.phase,
            chronological_order=project.chronological_order,
            universe_name=project.universe.name if project.universe else None,
            franchise_name=project.franchise.name if project.franchise else None,
            genre_names=tuple(g.name for g in project.genres),
            cast=cast,
            crew=crew,
            watched=user_data.watched if user_data else False,
            favorite=user_data.favorite if user_data else False,
            wishlist=user_data.wishlist if user_data else False,
            skipped=user_data.skipped if user_data else False,
            rating=user_data.rating if user_data else None,
            notes=user_data.notes if user_data else None,
            rewatch_count=user_data.rewatch_count if user_data else 0,
            last_watched_date=user_data.last_watched_date if user_data else None,
            watch_history=watch_history,
            previous_in_timeline=_timeline_neighbor(session, project.chronological_order, "previous"),
            next_in_timeline=_timeline_neighbor(session, project.chronological_order, "next"),
            tmdb_id=project.tmdb_id,
        )
    return detail


def _timeline_neighbor(session, chronological_order: int | None, direction: str) -> TimelineNeighbor | None:
    """The adjacent project in chronological_order, or None if this
    project has no chronological_order of its own (most one-shots,
    documentaries, and non-canon content) or is already at that end of
    the timeline."""
    if chronological_order is None:
        return None

    stmt = select(Project.id, Project.title, Project.chronological_order).where(
        Project.chronological_order.is_not(None)
    )
    if direction == "previous":
        stmt = stmt.where(Project.chronological_order < chronological_order).order_by(
            Project.chronological_order.desc()
        )
    else:
        stmt = stmt.where(Project.chronological_order > chronological_order).order_by(
            Project.chronological_order.asc()
        )

    row = session.execute(stmt.limit(1)).first()
    if row is None:
        return None
    return TimelineNeighbor(id=row.id, title=row.title, chronological_order=row.chronological_order)


# Sentinel distinguishing "field not supplied" from "field explicitly set to
# None" (e.g. clearing a rating or notes) in update_user_project_data below.
_UNSET = object()


def _get_or_create_user_data(session, project_id: int) -> UserProjectData:
    user_data = session.scalar(
        select(UserProjectData).where(UserProjectData.project_id == project_id)
    )
    if user_data is None:
        user_data = UserProjectData(project_id=project_id)
        session.add(user_data)
    return user_data


def update_user_project_data(
    project_id: int,
    *,
    watched: bool | object = _UNSET,
    favorite: bool | object = _UNSET,
    wishlist: bool | object = _UNSET,
    skipped: bool | object = _UNSET,
    rating: float | None | object = _UNSET,
    notes: str | None | object = _UNSET,
) -> ProjectDetail:
    """Create or update the UserProjectData row for a project.

    Any argument left at its default (``_UNSET``) is left untouched; pass
    an explicit value -- including ``None`` to clear a rating or notes --
    to change it. Never touches canonical Project fields, keeping the
    "API refresh can never clobber user data" guarantee intact. Owns its
    own session scope and returns a fresh :class:`ProjectDetail`.

    Raises ``ValueError`` if no project with that id exists.
    """
    with session_scope() as session:
        if session.get(Project, project_id) is None:
            raise ValueError(f"No project with id={project_id}")

        user_data = _get_or_create_user_data(session, project_id)

        if watched is not _UNSET:
            user_data.watched = bool(watched)
        if favorite is not _UNSET:
            user_data.favorite = bool(favorite)
        if wishlist is not _UNSET:
            user_data.wishlist = bool(wishlist)
        if skipped is not _UNSET:
            user_data.skipped = bool(skipped)
        if rating is not _UNSET:
            user_data.rating = rating
        if notes is not _UNSET:
            user_data.notes = notes

    detail = get_project_detail(project_id)
    assert detail is not None  # the project existed a moment ago in this same call
    return detail


def get_surprise_me_pick() -> int | None:
    """A random, not-yet-watched, not-skipped RELEASED project id -- for
    the "Surprise Me" button, when the user can't decide what to watch
    next. Unlike statistics_service's "Up Next" (which requires
    chronological_order and always returns the *same* next pick),
    this is a genuine random draw over the whole eligible catalog and
    returns something different each call, and doesn't require
    chronological_order to be set at all -- so it can surface one-shots,
    documentaries, and other chronologically-unordered content too, not
    just the main chronological line.

    Returns None if there's nothing eligible left (everything released
    has already been watched or skipped, or the catalog is empty).
    """
    with session_scope() as session:
        row = session.execute(
            select(Project.id)
            .outerjoin(UserProjectData, UserProjectData.project_id == Project.id)
            .where(
                Project.status == ProjectStatus.RELEASED,
                UserProjectData.watched.is_not(True),
                UserProjectData.skipped.is_not(True),
            )
            .order_by(func.random())
            .limit(1)
        ).first()
    return row.id if row is not None else None


def log_watch(project_id: int, *, notes: str | None = None, watched_with: str | None = None) -> ProjectDetail:
    """Record a watch event for a project: appends a WatchHistoryEntry,
    marks it watched, stamps today as the last-watched date, and -- if it
    was already watched -- increments rewatch_count. Owns its own session
    scope and returns a fresh :class:`ProjectDetail`.

    Raises ``ValueError`` if no project with that id exists.
    """
    with session_scope() as session:
        if session.get(Project, project_id) is None:
            raise ValueError(f"No project with id={project_id}")

        user_data = _get_or_create_user_data(session, project_id)

        is_rewatch = user_data.watched
        if is_rewatch:
            user_data.rewatch_count += 1
        user_data.watched = True
        user_data.last_watched_date = date.today()

        session.add(
            WatchHistoryEntry(
                project_id=project_id,
                is_rewatch=is_rewatch,
                notes=notes,
                watched_with=watched_with,
            )
        )

    detail = get_project_detail(project_id)
    assert detail is not None  # the project existed a moment ago in this same call
    return detail
