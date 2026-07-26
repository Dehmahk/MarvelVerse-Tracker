"""Cleans up duplicate projects created by a real, observed TMDB
data-quality issue: TMDB itself sometimes carries more than one listing
for the same real-world show or film (e.g. an early, orphaned
"cancelled" placeholder entry alongside the real, released one). Before
services.tmdb_sync_service.sync_from_tmdb() started guarding against
this (see its _find_likely_existing_duplicate()), a sync could create
one of these duplicate pairs as two separate Project rows.

This module is for cleaning up duplicates that *already* exist in a
database from before that guard was added. It is deliberately far more
conservative than services.data_integrity_service (which only ever
reports issues, never touches anything): this module *does* delete
rows, but only when doing so is provably safe -- see
find_cleanup_candidates()'s and clean_up_duplicates()'s own
docstrings for exactly what "safe" means here.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select

from database import session_scope
from models import CollectionProject, Episode, Project, UserProjectData, WatchHistoryEntry


@dataclass(frozen=True)
class DuplicateCleanupCandidate:
    """One duplicate pair found by find_cleanup_candidates(). `keep`
    is the project that would remain; `remove` is the one that would
    be deleted. `remove_has_personal_data` being True means this pair
    is NOT safe to auto-clean -- it's surfaced for a person to look at
    and decide on manually instead."""

    keep_id: int
    keep_title: str
    remove_id: int
    remove_title: str
    remove_has_personal_data: bool
    remove_personal_data_summary: str | None


def _project_completeness_score(project: Project) -> int:
    """A rough "how much real data does this project actually have"
    score, used only to pick which of a duplicate pair to keep -- never
    used for anything else. Higher is more complete."""
    score = 0
    if project.poster_path:
        score += 3
    if project.synopsis:
        score += 2
    if project.background_path:
        score += 1
    if project.runtime_minutes:
        score += 1
    if project.studio:
        score += 1
    if project.status.value not in ("cancelled",):
        score += 5  # a real, non-cancelled status strongly suggests this is the "real" entry
    return score


def _describe_personal_data(session, project_id: int) -> str | None:
    """A short, human-readable summary of what personal data exists on
    `project_id`, or None if there's genuinely none at all. Used both
    to decide whether a duplicate is safe to auto-remove and to tell
    the person exactly what they'd be looking at if it isn't."""
    parts: list[str] = []

    user_data = session.scalar(select(UserProjectData).where(UserProjectData.project_id == project_id))
    if user_data is not None:
        if user_data.watched:
            parts.append("marked watched")
        if user_data.rating is not None:
            parts.append(f"rated {user_data.rating:g}")
        if user_data.favorite:
            parts.append("favorited")
        if user_data.wishlist:
            parts.append("on wishlist")
        if user_data.notes:
            parts.append("has notes")
        if user_data.rewatch_count:
            parts.append(f"rewatched {user_data.rewatch_count}x")

    watch_history_count = session.scalar(
        select(WatchHistoryEntry).where(WatchHistoryEntry.project_id == project_id).limit(1)
    )
    if watch_history_count is not None:
        parts.append("has watch history entries")

    watched_episode = session.scalar(
        select(Episode).where(Episode.project_id == project_id, Episode.watched.is_(True)).limit(1)
    )
    if watched_episode is not None:
        parts.append("has watched episodes")

    in_collection = session.scalar(
        select(CollectionProject).where(CollectionProject.project_id == project_id).limit(1)
    )
    if in_collection is not None:
        parts.append("is in a collection")

    if not parts:
        return None
    return ", ".join(parts)


def find_cleanup_candidates() -> tuple[DuplicateCleanupCandidate, ...]:
    """Finds duplicate pairs -- same title, release date in the same
    year, different tmdb_id -- the same conservative matching
    services.tmdb_sync_service._find_likely_existing_duplicate() uses
    going forward. For each pair, picks which one looks more complete
    to keep, and checks whether the other one has any personal data on
    it at all.

    Read-only -- this only reports what *could* be cleaned up. Use
    clean_up_duplicates() to actually remove the ones that are safe.
    """
    candidates: list[DuplicateCleanupCandidate] = []

    with session_scope() as session:
        all_projects = session.scalars(
            select(Project).where(Project.tmdb_id.is_not(None), Project.release_date.is_not(None))
        ).all()

        groups: dict[tuple[str, int], list[Project]] = defaultdict(list)
        for project in all_projects:
            key = (project.title.strip().casefold(), project.release_date.year)
            groups[key].append(project)

        for group in groups.values():
            if len(group) < 2:
                continue
            # More than 2 in a group is unusual and worth a person's
            # attention rather than this module guessing at pairing --
            # only handle the simple, common two-way case.
            if len(group) > 2:
                continue

            ranked = sorted(group, key=_project_completeness_score, reverse=True)
            keep, remove = ranked[0], ranked[1]

            personal_data_summary = _describe_personal_data(session, remove.id)
            candidates.append(
                DuplicateCleanupCandidate(
                    keep_id=keep.id,
                    keep_title=keep.title,
                    remove_id=remove.id,
                    remove_title=remove.title,
                    remove_has_personal_data=personal_data_summary is not None,
                    remove_personal_data_summary=personal_data_summary,
                )
            )

    return tuple(candidates)


def clean_up_duplicates() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Actually removes the "remove" side of every candidate that has
    NO personal data on it at all -- the only case this module ever
    acts on automatically. Any candidate whose "remove" side has any
    personal data (watched status, a rating, notes, watch history,
    watched episodes, collection membership -- anything) is left
    completely untouched, full stop, no matter how confident the
    title/year match looks.

    Returns (removed_descriptions, needs_manual_review_descriptions).
    """
    candidates = find_cleanup_candidates()
    removed: list[str] = []
    needs_review: list[str] = []

    with session_scope() as session:
        for candidate in candidates:
            if candidate.remove_has_personal_data:
                needs_review.append(
                    f'"{candidate.remove_title}" (id={candidate.remove_id}) looks like a duplicate of '
                    f'"{candidate.keep_title}" (id={candidate.keep_id}), but has personal data on it '
                    f"({candidate.remove_personal_data_summary}) -- left untouched, review manually."
                )
                continue

            project = session.get(Project, candidate.remove_id)
            if project is None:
                continue  # already gone somehow -- nothing to do
            session.delete(project)
            removed.append(f'"{candidate.remove_title}" (id={candidate.remove_id}) -- duplicate of "{candidate.keep_title}"')

    return tuple(removed), tuple(needs_review)
