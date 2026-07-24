from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from database import session_scope
from models import Project, ProjectStatus, ProjectType

logger = logging.getLogger(__name__)


class TimelineSortMode(str, Enum):
    """How :func:`get_timeline` should order/bucket its results.

    ``PHASE`` (the default) is the existing saga/phase-grouped view.
    ``CHRONOLOGICAL`` ignores saga/phase entirely and returns one flat,
    ungrouped run of every entry in pure in-story order (falling back to
    release_date, then title, exactly like the per-group ordering below)
    -- i.e. "1, 2, 3, 4, ..." straight through the whole catalog. Inherits
    ``str`` so callers can pass either the enum member or its plain
    ``"phase"``/``"chronological"`` value interchangeably (handy at the
    view/controller boundary, which only deals in primitives)."""

    PHASE = "phase"
    CHRONOLOGICAL = "chronological"


# Default sagas excluded from CHRONOLOGICAL sort_mode: real in-story viewing
# order for canon films/shows belongs in Phase sorting, but documentaries,
# one-off making-of specials, and junior/spin-off shows aren't part of any
# in-story timeline, so they'd only clutter a strict rewatch-order list with
# entries that have no real chronological placement. Excluded from
# CHRONOLOGICAL sort_mode only; PHASE sort_mode still shows them under their
# own saga headers. This is only the *default* -- get_timeline()'s
# excluded_sagas parameter lets a caller (the controller, driven by
# AppConfig.timeline_excluded_sagas from the Settings > Timeline panel)
# override which sagas get skipped, per-catalog.
SAGAS_EXCLUDED_FROM_CHRONOLOGICAL: frozenset[str] = frozenset(
    {
        "Documentaries & Making-Of",
        "Marvel Studios Specials & Extras",
        "Junior & Spin-off Shows",
    }
)


@dataclass(frozen=True)
class TimelineEntry:
    """A flat, detached-safe read model for one marker on the Timeline
    page. Built entirely inside the owning session_scope, like every
    other read model in this codebase, so callers (views, controllers)
    never touch a lazy-loaded ORM instance after the session that
    produced it has closed."""

    id: int
    title: str
    slug: str
    project_type: ProjectType
    status: ProjectStatus
    release_date: date | None
    chronological_order: int | None
    poster_path: str | None
    watched: bool
    favorite: bool
    rating: float | None


@dataclass(frozen=True)
class TimelineGroup:
    """A run of :class:`TimelineEntry` sharing the same saga/phase, in
    the same order the timeline as a whole is sorted in. ``saga``/``phase``
    are ``None`` for projects that have neither set -- they still get a
    group (rather than being dropped) so nothing silently disappears."""

    saga: str | None
    phase: str | None
    entries: tuple[TimelineEntry, ...]


def get_timeline(
    universe_id: int | None = None,
    sort_mode: TimelineSortMode | str = TimelineSortMode.PHASE,
    excluded_sagas: frozenset[str] | set[str] = SAGAS_EXCLUDED_FROM_CHRONOLOGICAL,
) -> tuple[TimelineGroup, ...]:
    """Build the full Timeline, optionally narrowed to one universe.

    Projects are ordered by ``chronological_order`` first (in-universe
    story order), falling back to ``release_date`` for anything without
    one, with ``title`` as a final, deterministic tiebreak. Projects with
    neither a ``chronological_order`` nor a ``release_date`` (e.g. an
    announced-but-undated sequel -- ``Avengers: Secret Wars`` in the seed
    data) sort last rather than disappearing, since both null-handling
    rules push them to the end.

    ``sort_mode`` picks how that ordered run gets bucketed:

    * ``TimelineSortMode.PHASE`` (the default) buckets entries into
      :class:`TimelineGroup` by ``(saga, phase)``, keeping each group's
      own entries in the same in-story chronological order as the flat
      list. The groups themselves, however, are ordered by each group's
      *earliest release date* rather than by which group happened to
      appear first in the in-story list. Those two orderings usually
      agree, but not always: a prequel like ``Captain Marvel`` (a Phase
      Three release set in-story right after ``Captain America: The
      First Avenger``) would otherwise drag a "Phase Three" header in
      front of "Phase Two" the moment it's reached, since it's the first
      Phase Three project encountered in story order. Sorting groups by
      release date instead keeps phase headers in their real-world
      release sequence (Phase One, Two, Three, ...) while still letting
      prequels sit in their correct in-story position *within* their own
      phase's entry list. Groups with no dated entries at all fall back
      to their original first-appearance position so they never
      disappear.
    * ``TimelineSortMode.CHRONOLOGICAL`` skips grouping altogether and
      returns a single :class:`TimelineGroup` (``saga=None, phase=None``)
      holding every entry in that same in-story order, uninterrupted --
      "1, 2, 3, 4, ..." straight through the whole catalog, the way a
      strict in-universe rewatch order would. Projects whose ``saga`` is
      in ``excluded_sagas`` (by default,
      :data:`SAGAS_EXCLUDED_FROM_CHRONOLOGICAL` -- documentaries/making-of
      specials, Marvel Studios specials & extras, junior/spin-off shows --
      none of which have a real in-story placement) are left out of this
      flat run entirely. They're unaffected in ``PHASE`` mode, where they
      still appear grouped under their own saga headers.

    Owns its own session scope, like every other function in this
    module; returns only detached DTOs, never live ORM instances.
    """
    sort_mode = TimelineSortMode(sort_mode)

    with session_scope() as session:
        stmt = select(Project).options(joinedload(Project.user_data))
        if universe_id is not None:
            stmt = stmt.where(Project.universe_id == universe_id)
        stmt = stmt.order_by(
            Project.chronological_order.asc().nulls_last(),
            Project.release_date.asc().nulls_last(),
            Project.title.asc(),
        )
        projects = session.scalars(stmt).unique().all()

        entries: list[TimelineEntry] = []
        chronological_entries: list[TimelineEntry] = []
        group_order: list[tuple[str | None, str | None]] = []
        grouped: dict[tuple[str | None, str | None], list[TimelineEntry]] = {}

        for project in projects:
            user_data = project.user_data
            entry = TimelineEntry(
                id=project.id,
                title=project.title,
                slug=project.slug,
                project_type=project.project_type,
                status=project.status,
                release_date=project.release_date,
                chronological_order=project.chronological_order,
                poster_path=project.poster_path,
                watched=user_data.watched if user_data else False,
                favorite=user_data.favorite if user_data else False,
                rating=user_data.rating if user_data else None,
            )
            entries.append(entry)
            if project.saga not in excluded_sagas:
                chronological_entries.append(entry)

            key = (project.saga, project.phase)
            if key not in grouped:
                grouped[key] = []
                group_order.append(key)
            grouped[key].append(entry)

        if sort_mode is TimelineSortMode.CHRONOLOGICAL:
            groups = (TimelineGroup(saga=None, phase=None, entries=tuple(chronological_entries)),)
        else:

            def _group_release_key(
                key: tuple[str | None, str | None], first_appearance_index: int
            ) -> tuple:
                dated_releases = [
                    entry.release_date for entry in grouped[key] if entry.release_date is not None
                ]
                if dated_releases:
                    return (0, min(dated_releases), first_appearance_index)
                return (1, date.max, first_appearance_index)

            ordered_keys = sorted(
                group_order,
                key=lambda key: _group_release_key(key, group_order.index(key)),
            )

            groups = tuple(
                TimelineGroup(saga=key[0], phase=key[1], entries=tuple(grouped[key]))
                for key in ordered_keys
            )

    logger.debug(
        "get_timeline(universe_id=%s, sort_mode=%s): %d groups across %d projects",
        universe_id,
        sort_mode,
        len(groups),
        len(projects),
    )
    return groups


def get_distinct_sagas() -> list[str]:
    """Every distinct, non-null ``Project.saga`` value in the catalog,
    alphabetically. Powers Settings > Timeline's "exclude from
    Chronological sort" checklist -- letting the user pick which sagas
    to exclude requires knowing what sagas actually exist, and that list
    isn't static (TMDB syncs and reference-data updates can add new
    ones), so this is a live query rather than a hardcoded constant."""
    with session_scope() as session:
        sagas = session.scalars(
            select(Project.saga).where(Project.saga.is_not(None)).distinct().order_by(Project.saga)
        ).all()
    return list(sagas)
