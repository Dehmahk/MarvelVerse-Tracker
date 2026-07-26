"""Episode-level watch tracking -- lets a TV show be tracked
episode-by-episode instead of only as a single watched/unwatched unit.

Episode rows are generated locally the first time a show's episodes are
looked at (see ensure_episodes_exist), distributed evenly across
season_count/episode_count with generic "Episode N" titles and no air
date/runtime/summary. Real values for those three fields only ever come
from an actual TMDB per-season sync (see sync_episodes_from_tmdb, which
requires the project to already have a real tmdb_id) -- never guessed
or written from memory, the same policy this app already applies to the
Dashboard's "Fact of the Day" list.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select

from database import session_scope
from models import Episode, Project


@dataclass(frozen=True)
class EpisodeItem:
    id: int
    season_number: int
    episode_number: int
    title: str | None
    air_date: date | None
    runtime_minutes: int | None
    summary: str | None
    watched: bool
    watched_at: datetime | None

    @property
    def display_title(self) -> str:
        return self.title or f"Episode {self.episode_number}"


def _distribute_episodes_per_season(season_count: int, episode_count: int) -> list[int]:
    """Splits `episode_count` total episodes across `season_count`
    seasons as evenly as possible (e.g. 13 episodes over 4 seasons ->
    [4, 3, 3, 3]) -- this app only knows the two aggregate numbers, not
    each season's real individual count, so an even split is the best
    available approximation."""
    base = episode_count // season_count
    remainder = episode_count % season_count
    # The first `remainder` seasons get one extra episode each, rather
    # than always piling every leftover onto the last season -- purely
    # a cosmetic choice, there's no real data either way to be "more
    # correct" about.
    return [base + 1 if i < remainder else base for i in range(season_count)]


def ensure_episodes_exist(project_id: int) -> bool:
    """Generates Episode rows for `project_id` from its season_count/
    episode_count if none exist yet. Safe to call every time episodes
    for a project are about to be displayed -- a no-op if rows already
    exist. Returns True if generation actually happened (mostly useful
    for tests), False if there was nothing to do (already generated, or
    the project has no season_count/episode_count set to generate from).
    """
    with session_scope() as session:
        project = session.get(Project, project_id)
        if project is None:
            return False

        already_exists = session.scalar(
            select(Episode.id).where(Episode.project_id == project_id).limit(1)
        )
        if already_exists is not None:
            return False

        if not project.season_count or not project.episode_count:
            return False

        per_season = _distribute_episodes_per_season(project.season_count, project.episode_count)
        for season_number, count_this_season in enumerate(per_season, start=1):
            for episode_number in range(1, count_this_season + 1):
                session.add(
                    Episode(
                        project_id=project_id,
                        season_number=season_number,
                        episode_number=episode_number,
                    )
                )
        return True


def get_episodes(project_id: int) -> tuple[EpisodeItem, ...]:
    """Every episode for `project_id`, ordered by season then episode
    number. Does NOT call ensure_episodes_exist itself -- the caller
    (the controller) is expected to call that first, same separation
    every other service function in this app keeps between "make sure
    the data exists" and "read the data.\""""
    with session_scope() as session:
        rows = session.scalars(
            select(Episode)
            .where(Episode.project_id == project_id)
            .order_by(Episode.season_number, Episode.episode_number)
        ).all()
        return tuple(
            EpisodeItem(
                id=e.id,
                season_number=e.season_number,
                episode_number=e.episode_number,
                title=e.title,
                air_date=e.air_date,
                runtime_minutes=e.runtime_minutes,
                summary=e.summary,
                watched=e.watched,
                watched_at=e.watched_at,
            )
            for e in rows
        )


def get_episode_progress(project_id: int) -> tuple[int, int]:
    """(watched_count, total_count) for `project_id` -- (0, 0) if no
    episodes have been generated for it yet."""
    with session_scope() as session:
        rows = session.scalars(select(Episode).where(Episode.project_id == project_id)).all()
        total_count = len(rows)
        watched_count = sum(1 for e in rows if e.watched)
        return watched_count, total_count


def set_episode_watched(episode_id: int, watched: bool) -> None:
    """Toggles a single episode's watched state, stamping (or clearing)
    watched_at to match."""
    with session_scope() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise ValueError(f"No episode with id={episode_id}")
        episode.watched = watched
        episode.watched_at = datetime.now() if watched else None


def mark_season_watched(project_id: int, season_number: int, watched: bool) -> None:
    """Marks every episode in one season watched/unwatched at once --
    the common case of "I watched all of Season 2" without needing to
    click every episode individually."""
    with session_scope() as session:
        rows = session.scalars(
            select(Episode).where(Episode.project_id == project_id, Episode.season_number == season_number)
        ).all()
        now = datetime.now() if watched else None
        for episode in rows:
            episode.watched = watched
            episode.watched_at = now


def sync_episodes_from_tmdb(project_id: int, api_key: str, *, client=None) -> bool:
    """Pulls real episode data (title, air date, runtime, TMDB's own
    synopsis) from TMDB for every season of `project_id`, creating
    Episode rows if they don't exist yet or updating them in place if
    they do (matched by season_number/episode_number, same "upsert by
    stable identity" pattern sync_from_tmdb uses for projects
    themselves). Requires the project to already have a real tmdb_id
    (e.g. from the automatic sync, or a manual "Find on TMDB" link) --
    raises ValueError if it doesn't, rather than silently doing nothing
    or falling back to guessed data.

    `client` can be injected for testing, same as sync_from_tmdb();
    a real TMDBClient is constructed from `api_key` otherwise.

    Never touches `watched`/`watched_at` on an existing episode --
    exactly like a project-level sync never touches UserProjectData,
    this is real/canonical data being refreshed, not personal tracking
    state.
    """
    from services.tmdb_client import TMDBClient

    with session_scope() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise ValueError(f"No project with id={project_id}")
        if not project.tmdb_id:
            raise ValueError(
                f'"{project.title}" has no linked TMDB entry yet -- use "Find on TMDB" '
                "to link it first, then real episode data can sync."
            )
        if not project.season_count:
            raise ValueError(f'"{project.title}" has no season count set -- nothing to sync episodes for.')

        tmdb = client or TMDBClient(api_key)
        tmdb_id = project.tmdb_id
        season_count = project.season_count

        existing_by_identity = {
            (e.season_number, e.episode_number): e
            for e in session.scalars(select(Episode).where(Episode.project_id == project_id)).all()
        }

        for season_number in range(1, season_count + 1):
            season_data = tmdb.get_tv_season_details(tmdb_id, season_number)
            for raw_episode in season_data.get("episodes", []):
                episode_number = raw_episode.get("episode_number")
                if episode_number is None:
                    continue

                identity = (season_number, episode_number)
                episode = existing_by_identity.get(identity)
                if episode is None:
                    episode = Episode(
                        project_id=project_id,
                        season_number=season_number,
                        episode_number=episode_number,
                    )
                    session.add(episode)
                    existing_by_identity[identity] = episode

                episode.title = raw_episode.get("name") or episode.title
                air_date_str = raw_episode.get("air_date")
                if air_date_str:
                    episode.air_date = date.fromisoformat(air_date_str)
                episode.runtime_minutes = raw_episode.get("runtime") or episode.runtime_minutes
                episode.summary = raw_episode.get("overview") or episode.summary

        return True
