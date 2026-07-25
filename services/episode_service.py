"""Episode-level watch tracking -- lets a TV show be tracked
episode-by-episode instead of only as a single watched/unwatched unit.

Episode rows are generated locally the first time a show's episodes are
looked at (see ensure_episodes_exist), distributed evenly across
season_count/episode_count with generic "Episode N" titles -- this app
has no live per-episode TMDB sync, so there's no real per-episode title/
air-date data to populate instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from database import session_scope
from models import Episode, Project


@dataclass(frozen=True)
class EpisodeItem:
    id: int
    season_number: int
    episode_number: int
    title: str | None
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
