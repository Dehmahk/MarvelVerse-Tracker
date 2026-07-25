"""Maps TMDB API responses onto this application's canonical models.

`sync_from_tmdb()` is the milestone-8 entry point: it discovers Marvel
Studios movies via `services.tmdb_client`, and (by default) TV series from
*both* Marvel Studios and Marvel Television -- two distinct TMDB companies,
since the 2013-2020 ABC/Netflix/Hulu/Freeform slate (Agents of S.H.I.E.L.D.,
Agent Carter, Daredevil, ...) was produced under the latter, separate label
and was invisible to this sync until both were discovered. It upserts
`Project`/`Person`/`ProjectCast`/`ProjectCrew`/`Genre` rows.

Two rules this module never breaks:

1. Idempotent -- matched by `Project.tmdb_id`/`Person.tmdb_id`, so re-running
   a sync updates existing rows in place rather than duplicating them.
2. Additive-only with respect to `UserProjectData` -- this module never
   imports, reads, or writes that table. A re-sync can never clobber a
   watched flag, rating, note, favorite, or wishlist entry.

It also never touches `universe_id`, `franchise_id`, `saga`, `phase`,
`chronological_order`, `in_universe_date`, `season_count`,
`episode_count`, `cancelled_date`, `next_season_release_date`, or
`production_start_date` on an existing project -- TMDB has no concept of
this app's MCU phase/saga/franchise groupings or in-story timeline
placement, and this app doesn't currently pull season/episode counts,
cancellation/next-season dates, or production start dates from TMDB
either, so all of those stay whatever a human (or a future, smarter
mapping) set them to. New projects are created with those fields left
`NULL`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import session_scope
from models import Genre, Person, Project, ProjectCast, ProjectCrew, ProjectStatus, ProjectType
from services.tmdb_client import (
    MARVEL_STUDIOS_FALLBACK_COMPANY_ID,
    MARVEL_TELEVISION_FALLBACK_COMPANY_ID,
    TMDBClient,
    TMDBError,
    image_url,
)

logger = logging.getLogger(__name__)

# Cast/crew are capped per project purely to keep sync fast and the detail
# page's cast/crew lists a sane length -- TMDB can return 50+ credits for
# an ensemble film or a long-running series.
MAX_CAST_PER_PROJECT = 15
MAX_CREW_PER_PROJECT = 8

# TMDB's crew list includes dozens of niche jobs (e.g. "Foley Artist");
# only these show up anywhere in this app's UI, so only these are recorded.
CREW_JOBS_OF_INTEREST = {
    "Director",
    "Writer",
    "Screenplay",
    "Story",
    "Producer",
    "Executive Producer",
    "Original Music Composer",
}

_STATUS_MAP = {
    "Released": ProjectStatus.RELEASED,
    "Ended": ProjectStatus.RELEASED,
    "Canceled": ProjectStatus.CANCELLED,
    "Cancelled": ProjectStatus.CANCELLED,
    "In Production": ProjectStatus.IN_PRODUCTION,
    "Returning Series": ProjectStatus.IN_PRODUCTION,
    "Post Production": ProjectStatus.IN_PRODUCTION,
    "Planned": ProjectStatus.ANNOUNCED,
    "Pilot": ProjectStatus.ANNOUNCED,
    "Rumored": ProjectStatus.ANNOUNCED,
}


@dataclass
class SyncResult:
    """A plain summary of one `sync_from_tmdb()` run -- built for both a
    log line and a Settings-page status message, never a live ORM object."""

    movies_created: int = 0
    movies_updated: int = 0
    tv_created: int = 0
    tv_updated: int = 0
    people_created: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_created(self) -> int:
        return self.movies_created + self.tv_created

    @property
    def total_updated(self) -> int:
        return self.movies_updated + self.tv_updated

    def summary(self) -> str:
        if self.total_created == 0 and self.total_updated == 0 and not self.errors:
            return "Nothing to sync."
        parts = [f"{self.total_created} added, {self.total_updated} updated"]
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        return ", ".join(parts)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "untitled"


def _unique_slug(session: Session, base_slug: str, *, tmdb_id: int) -> str:
    """Appends the tmdb id if `base_slug` collides with a different
    project's slug (e.g. two TMDB titles that happen to render identically).
    Never touches an existing project's own slug on a re-sync."""
    existing = session.scalar(select(Project).where(Project.slug == base_slug))
    if existing is None or existing.tmdb_id == tmdb_id:
        return base_slug
    return f"{base_slug}-{tmdb_id}"


def _map_status(raw_status: str | None, release_date: date | None) -> ProjectStatus:
    if raw_status and raw_status in _STATUS_MAP:
        return _STATUS_MAP[raw_status]
    # Fall back to inferring from the release date if TMDB gave us a blank
    # or unrecognized status string, rather than defaulting everything that
    # slips through to ANNOUNCED regardless of whether it already aired.
    if release_date and release_date <= date.today():
        return ProjectStatus.RELEASED
    return ProjectStatus.ANNOUNCED


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def resolve_marvel_studios_company_id(client: TMDBClient) -> int:
    """Looks up the live TMDB company id for "Marvel Studios" by name
    rather than trusting a hardcoded constant. Falls back to the known id
    (`MARVEL_STUDIOS_FALLBACK_COMPANY_ID`) only if the live search comes
    back empty, so a future TMDB catalog change can't silently strand this
    app on a stale/wrong id."""
    results = client.search_company("Marvel Studios")
    for company in results:
        if (company.get("name") or "").strip().lower() == "marvel studios":
            return company["id"]
    if results:
        return results[0]["id"]
    logger.warning(
        "TMDB company search for 'Marvel Studios' returned nothing; "
        "falling back to the known company id."
    )
    return MARVEL_STUDIOS_FALLBACK_COMPANY_ID


def resolve_marvel_television_company_id(client: TMDBClient) -> int:
    """Looks up the live TMDB company id for "Marvel Television" -- the
    2013-2020 ABC/Netflix/Hulu/Freeform production label responsible for
    Agents of S.H.I.E.L.D., Agent Carter, and the Defenders shows. This is
    a *different* TMDB company from Marvel Studios; a sync that only ever
    discovered Marvel Studios's catalog would never see any of this slate,
    which is exactly what happened before this function existed. Falls
    back to the known id the same way `resolve_marvel_studios_company_id`
    does, for the same reason."""
    results = client.search_company("Marvel Television")
    for company in results:
        if (company.get("name") or "").strip().lower() == "marvel television":
            return company["id"]
    if results:
        return results[0]["id"]
    logger.warning(
        "TMDB company search for 'Marvel Television' returned nothing; "
        "falling back to the known company id."
    )
    return MARVEL_TELEVISION_FALLBACK_COMPANY_ID


def _extract_trailer_url(videos: dict | None) -> str | None:
    """Picks the best trailer out of a TMDB details response's embedded
    `videos` object (see get_movie_details/get_tv_details's
    append_to_response=videos), or None if it has no YouTube trailer at
    all -- not every title does, especially older or lower-profile ones.

    Preference order: an official trailer first, then any trailer, then
    an official teaser, then any teaser -- a teaser is still a real,
    useful preview when a full trailer isn't available, but a genuine
    trailer is always the better pick when both exist. TMDB only ever
    returns this data for videos hosted on YouTube or Vimeo; anything
    not on YouTube is skipped, since the rest of this app's trailer
    handling (the URL parser, the thumbnail preview) is YouTube-specific.
    """
    if not videos:
        return None

    results = videos.get("results") or []
    youtube_videos = [v for v in results if v.get("site") == "YouTube" and v.get("key")]
    if not youtube_videos:
        return None

    def _pick(video_type: str, official_only: bool) -> dict | None:
        candidates = [v for v in youtube_videos if v.get("type") == video_type]
        if official_only:
            candidates = [v for v in candidates if v.get("official")]
        return candidates[0] if candidates else None

    best = (
        _pick("Trailer", official_only=True)
        or _pick("Trailer", official_only=False)
        or _pick("Teaser", official_only=True)
        or _pick("Teaser", official_only=False)
    )
    if best is None:
        return None
    return f"https://www.youtube.com/watch?v={best['key']}"


def _get_or_create_genre(session: Session, name: str) -> Genre:
    genre = session.scalar(select(Genre).where(Genre.name == name))
    if genre is None:
        genre = Genre(name=name, slug=_slugify(name))
        session.add(genre)
        session.flush()
    return genre


def _get_or_create_person(session: Session, raw_person: dict, *, people_created: list[int]) -> Person | None:
    tmdb_person_id = raw_person.get("id")
    name = (raw_person.get("name") or "").strip()
    if tmdb_person_id is None or not name:
        return None

    person = session.scalar(select(Person).where(Person.tmdb_id == tmdb_person_id))
    if person is not None:
        profile_path = raw_person.get("profile_path")
        if profile_path:
            person.photo_path = image_url(profile_path, size="w185")
        return person

    base_slug = _slugify(name)
    slug = base_slug
    suffix = 2
    while session.scalar(select(Person).where(Person.slug == slug)) is not None:
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    person = Person(
        name=name,
        slug=slug,
        photo_path=image_url(raw_person.get("profile_path"), size="w185"),
        tmdb_id=tmdb_person_id,
    )
    session.add(person)
    session.flush()
    people_created[0] += 1
    return person


def _sync_cast_and_crew(session: Session, project: Project, credits: dict, people_created: list[int]) -> None:
    # Canonical, API-owned data -- safe to fully replace every sync rather
    # than diffing row-by-row. UserProjectData is never touched here.
    project.cast.clear()
    project.crew.clear()
    session.flush()

    cast_entries = sorted(
        credits.get("cast", []), key=lambda c: c.get("order", 999)
    )[:MAX_CAST_PER_PROJECT]
    for billing_order, raw_cast in enumerate(cast_entries):
        person = _get_or_create_person(session, raw_cast, people_created=people_created)
        if person is None:
            continue
        project.cast.append(
            ProjectCast(
                person_id=person.id,
                character_name=raw_cast.get("character") or None,
                billing_order=billing_order,
            )
        )

    seen_crew: set[tuple[int, str]] = set()
    crew_added = 0
    for raw_crew in credits.get("crew", []):
        if crew_added >= MAX_CREW_PER_PROJECT:
            break
        job = raw_crew.get("job")
        if job not in CREW_JOBS_OF_INTEREST:
            continue
        person = _get_or_create_person(session, raw_crew, people_created=people_created)
        if person is None:
            continue
        key = (person.id, job)
        if key in seen_crew:
            continue
        seen_crew.add(key)
        project.crew.append(ProjectCrew(person_id=person.id, role=job))
        crew_added += 1


def _apply_common_fields(
    project: Project,
    *,
    title: str,
    synopsis: str | None,
    release_date: date | None,
    runtime_minutes: int | None,
    studio: str | None,
    poster_path: str | None,
    background_path: str | None,
    status: ProjectStatus,
    genre_objs: list[Genre],
    trailer_url: str | None = None,
) -> None:
    project.title = title
    project.synopsis = synopsis
    project.release_date = release_date
    project.runtime_minutes = runtime_minutes
    project.studio = studio
    project.poster_path = poster_path
    project.background_path = background_path
    project.status = status
    project.genres = genre_objs
    project.trailer_url = trailer_url
    # Deliberately NOT touched: universe_id, franchise_id, saga, phase,
    # chronological_order, in_universe_date, season_count, episode_count,
    # cancelled_date, next_season_release_date, production_start_date --
    # see the module docstring.


def _sync_movie(
    session: Session, client: TMDBClient, raw_summary: dict, result: SyncResult, people_created: list[int]
) -> None:
    tmdb_id = raw_summary["id"]
    try:
        details = client.get_movie_details(tmdb_id)
    except TMDBError as exc:
        result.errors.append(f"Movie tmdb_id={tmdb_id}: {exc}")
        return

    title = details.get("title") or details.get("original_title") or "Untitled"
    release_date = _parse_date(details.get("release_date"))
    status = _map_status(details.get("status"), release_date)
    genre_objs = [_get_or_create_genre(session, g["name"]) for g in details.get("genres", [])]
    production_companies = details.get("production_companies") or []
    studio = production_companies[0]["name"] if production_companies else None

    project = session.scalar(select(Project).where(Project.tmdb_id == tmdb_id))
    is_new = project is None
    if is_new:
        year = release_date.year if release_date else None
        base_slug = _slugify(f"{title}-{year}" if year else title)
        project = Project(
            slug=_unique_slug(session, base_slug, tmdb_id=tmdb_id),
            project_type=ProjectType.MOVIE,
            tmdb_id=tmdb_id,
            title=title,
            status=status,
        )
        session.add(project)

    _apply_common_fields(
        project,
        title=title,
        synopsis=details.get("overview") or None,
        release_date=release_date,
        runtime_minutes=details.get("runtime") or None,
        studio=studio,
        poster_path=image_url(details.get("poster_path")),
        background_path=image_url(details.get("backdrop_path"), size="w1280"),
        status=status,
        genre_objs=genre_objs,
        trailer_url=_extract_trailer_url(details.get("videos")),
    )
    session.flush()

    _sync_cast_and_crew(session, project, details.get("credits") or {}, people_created)

    if is_new:
        result.movies_created += 1
    else:
        result.movies_updated += 1


def _sync_tv(
    session: Session, client: TMDBClient, raw_summary: dict, result: SyncResult, people_created: list[int]
) -> None:
    tmdb_id = raw_summary["id"]
    try:
        details = client.get_tv_details(tmdb_id)
    except TMDBError as exc:
        result.errors.append(f"TV tmdb_id={tmdb_id}: {exc}")
        return

    title = details.get("name") or details.get("original_name") or "Untitled"
    release_date = _parse_date(details.get("first_air_date"))
    status = _map_status(details.get("status"), release_date)
    genre_objs = [_get_or_create_genre(session, g["name"]) for g in details.get("genres", [])]
    production_companies = details.get("production_companies") or []
    studio = production_companies[0]["name"] if production_companies else None
    episode_runtimes = details.get("episode_run_time") or []
    runtime_minutes = episode_runtimes[0] if episode_runtimes else None

    project = session.scalar(select(Project).where(Project.tmdb_id == tmdb_id))
    is_new = project is None
    if is_new:
        year = release_date.year if release_date else None
        base_slug = _slugify(f"{title}-{year}" if year else title)
        project = Project(
            slug=_unique_slug(session, base_slug, tmdb_id=tmdb_id),
            project_type=ProjectType.TV_SERIES,
            tmdb_id=tmdb_id,
            title=title,
            status=status,
        )
        session.add(project)

    _apply_common_fields(
        project,
        title=title,
        synopsis=details.get("overview") or None,
        release_date=release_date,
        runtime_minutes=runtime_minutes,
        studio=studio,
        poster_path=image_url(details.get("poster_path")),
        background_path=image_url(details.get("backdrop_path"), size="w1280"),
        status=status,
        genre_objs=genre_objs,
        trailer_url=_extract_trailer_url(details.get("videos")),
    )
    session.flush()

    _sync_cast_and_crew(session, project, details.get("credits") or {}, people_created)

    if is_new:
        result.tv_created += 1
    else:
        result.tv_updated += 1


def sync_from_tmdb(
    api_key: str,
    *,
    include_tv: bool = True,
    max_pages: int = 5,
    client: TMDBClient | None = None,
) -> SyncResult:
    """Pull Marvel Studios movies (and, by default, TV series) from TMDB
    and upsert them into `Project`/`Person`/`ProjectCast`/`ProjectCrew`/
    `Genre`. See the module docstring for the idempotency and
    additive-only-re-UserProjectData guarantees.

    `client` can be injected for testing; otherwise a real `TMDBClient` is
    constructed from `api_key`. A failure resolving the company id or
    fetching a discovery page propagates as whatever `TMDBClient` raises
    (`TMDBAuthError`, `TMDBConnectionError`, ...) -- once discovery
    succeeds, a failure on one item's detail fetch is recorded in
    `SyncResult.errors` instead of aborting the rest of the sync.
    """
    tmdb = client or TMDBClient(api_key)
    result = SyncResult()
    people_created = [0]

    company_id = resolve_marvel_studios_company_id(tmdb)

    with session_scope() as session:
        page = 1
        while page <= max_pages:
            movie_page = tmdb.discover_movies(company_id, page=page)
            for raw_summary in movie_page.get("results", []):
                _sync_movie(session, tmdb, raw_summary, result, people_created)
            if page >= movie_page.get("total_pages", page):
                break
            page += 1

        if include_tv:
            # Two separate TMDB companies produced MCU-connected TV series:
            # Marvel Studios (the Disney+ era, Phase Four onward) and the
            # earlier, now-folded-in "Marvel Television" label (Agents of
            # S.H.I.E.L.D., Agent Carter, the Netflix Defenders shows, ...).
            # Discovering only the first one is exactly how that entire
            # 2013-2020 slate went missing from every sync -- see
            # `resolve_marvel_television_company_id`'s docstring.
            tv_company_ids = [company_id, resolve_marvel_television_company_id(tmdb)]
            seen_tv_tmdb_ids: set[int] = set()
            for tv_company_id in tv_company_ids:
                page = 1
                while page <= max_pages:
                    tv_page = tmdb.discover_tv(tv_company_id, page=page)
                    for raw_summary in tv_page.get("results", []):
                        tmdb_id = raw_summary.get("id")
                        if tmdb_id in seen_tv_tmdb_ids:
                            continue  # a show co-credited to both companies
                        seen_tv_tmdb_ids.add(tmdb_id)
                        _sync_tv(session, tmdb, raw_summary, result, people_created)
                    if page >= tv_page.get("total_pages", page):
                        break
                    page += 1

    result.people_created = people_created[0]
    logger.info("TMDB sync complete: %s", result.summary())
    return result


@dataclass(frozen=True)
class TMDBSearchResult:
    """One candidate from search_tmdb() -- enough for the user to tell
    which (if any) is the project they meant."""

    tmdb_id: int
    title: str
    year: int | None
    overview: str


def search_tmdb(client: TMDBClient, query: str, project_type: ProjectType) -> list[TMDBSearchResult]:
    """Searches TMDB directly by title -- unlike sync_from_tmdb(), which
    only ever discovers titles attributed to a specific company (Marvel
    Studios' own TMDB entry), so it would never find Fox's X-Men films,
    Sony's Spider-Man/Venom films, New Line's Blade films, or anything
    else made by a studio other than Marvel Studios itself, even if
    TMDB has a perfectly good entry for it under that other studio.

    This is the read-only first step of manually linking one specific
    project to its real TMDB entry (see link_project_to_tmdb) when it
    wasn't going to be found by the automatic sync -- the user picks
    the right match out of these results themselves, since only they
    can actually verify it (this app has no way to confirm which
    result, if any, is correct)."""
    raw_results = (
        client.search_movie(query) if project_type == ProjectType.MOVIE else client.search_tv(query)
    )

    results = []
    for raw in raw_results:
        title = raw.get("title") or raw.get("name") or raw.get("original_title") or raw.get("original_name")
        date_str = raw.get("release_date") or raw.get("first_air_date")
        parsed_date = _parse_date(date_str)
        results.append(
            TMDBSearchResult(
                tmdb_id=raw["id"],
                title=title or "Untitled",
                year=parsed_date.year if parsed_date else None,
                overview=raw.get("overview") or "",
            )
        )
    return results


def link_project_to_tmdb(
    project_id: int,
    tmdb_id: int,
    project_type: ProjectType,
    api_key: str,
    *,
    client: TMDBClient | None = None,
) -> None:
    """Links an existing project (one with no tmdb_id of its own, e.g.
    one of the ~45 movies/shows added by hand rather than through a
    sync) to a specific TMDB entry the user picked out of search_tmdb()'s
    results, then immediately pulls that entry's full details onto it --
    synopsis, runtime, studio, poster/backdrop art, genres, trailer, and
    cast/crew, exactly like a real sync would, just for this one project
    instead of everything discoverable under Marvel Studios' company id.

    `client` can be injected for testing, same as sync_from_tmdb(); a
    real TMDBClient is constructed from `api_key` otherwise.

    Deliberately does NOT touch this app's own curation fields (universe,
    franchise, saga, phase, chronological_order, in_universe_date,
    season/episode counts, cancellation/next-season/production-start
    dates) -- same protection _apply_common_fields already gives every
    other synced project, see this module's own docstring."""
    tmdb = client or TMDBClient(api_key)

    with session_scope() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise ValueError(f"No project with id={project_id}")

        details = (
            tmdb.get_movie_details(tmdb_id)
            if project_type == ProjectType.MOVIE
            else tmdb.get_tv_details(tmdb_id)
        )

        if project_type == ProjectType.MOVIE:
            title = details.get("title") or details.get("original_title") or project.title
            release_date = _parse_date(details.get("release_date"))
            runtime_minutes = details.get("runtime") or None
        else:
            title = details.get("name") or details.get("original_name") or project.title
            release_date = _parse_date(details.get("first_air_date"))
            episode_runtimes = details.get("episode_run_time") or []
            runtime_minutes = episode_runtimes[0] if episode_runtimes else None

        status = _map_status(details.get("status"), release_date)
        genre_objs = [_get_or_create_genre(session, g["name"]) for g in details.get("genres", [])]
        production_companies = details.get("production_companies") or []
        studio = production_companies[0]["name"] if production_companies else None

        # tmdb_id has a UNIQUE constraint -- if some other project in the
        # library is already linked to this exact TMDB entry, saving
        # would otherwise fail with a raw, unhelpful database error.
        # This happens more often than it might seem: TMDB search
        # results for a query like "Agent Carter" surface both the TV
        # series *and* its own tie-in one-shot short as separate,
        # similarly-named entries, and it's an easy mix-up to pick the
        # one that's actually already linked to a different project.
        conflicting_project = session.scalar(
            select(Project).where(Project.tmdb_id == tmdb_id, Project.id != project_id)
        )
        if conflicting_project is not None:
            raise TMDBError(
                f'This TMDB entry is already linked to "{conflicting_project.title}" in your '
                "library. Search again and make sure you're picking the result for "
                f'"{project.title}" specifically, not a same-named short, one-shot, or spin-off.'
            )

        project.tmdb_id = tmdb_id
        _apply_common_fields(
            project,
            title=title,
            synopsis=details.get("overview") or None,
            release_date=release_date,
            runtime_minutes=runtime_minutes,
            studio=studio,
            poster_path=image_url(details.get("poster_path")),
            background_path=image_url(details.get("backdrop_path"), size="w1280"),
            status=status,
            genre_objs=genre_objs,
            trailer_url=_extract_trailer_url(details.get("videos")),
        )
        session.flush()

        people_created = [0]
        _sync_cast_and_crew(session, project, details.get("credits") or {}, people_created)
