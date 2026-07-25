""""Compare with a friend" -- reads someone else's exported personal-data
JSON file (see services.data_export_service.export_user_data) and
compares it against your own live watch data, without importing or
merging anything into your own library. Purely read-only on both sides:
your own data is only ever queried, never modified, and the friend's
file is only ever read, never written back to.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from database import session_scope
from models import Project, UserProjectData
from services.data_export_service import EXPORT_FORMAT_VERSION


class ComparisonFileError(Exception):
    """Raised for a friend's export file that can't be read as a valid
    export -- missing, corrupt JSON, or an unrecognized format_version."""


@dataclass(frozen=True)
class ComparisonItem:
    slug: str
    title: str
    my_rating: float | None
    friend_rating: float | None


@dataclass(frozen=True)
class ComparisonResult:
    """The full comparison between your own library and a friend's
    exported data. `neither_watched_count` is a plain count rather than
    a full list -- for most libraries that's the largest bucket by far,
    and there's nothing meaningful to show per-item for something
    neither of you has seen."""

    both_watched: tuple[ComparisonItem, ...]
    only_me_watched: tuple[ComparisonItem, ...]
    only_friend_watched: tuple[ComparisonItem, ...]
    neither_watched_count: int

    @property
    def total_projects(self) -> int:
        return (
            len(self.both_watched)
            + len(self.only_me_watched)
            + len(self.only_friend_watched)
            + self.neither_watched_count
        )

    @property
    def overlap_percent(self) -> int:
        watched_by_either = len(self.both_watched) + len(self.only_me_watched) + len(self.only_friend_watched)
        if watched_by_either == 0:
            return 0
        return round(100 * len(self.both_watched) / watched_by_either)


def _load_friend_export(export_path: Path) -> dict:
    if not export_path.exists():
        raise ComparisonFileError(f"File not found: {export_path}")

    try:
        data = json.loads(export_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ComparisonFileError(f"Couldn't read this file as a valid export: {exc}") from exc

    if not isinstance(data, dict) or "format_version" not in data or "projects" not in data:
        raise ComparisonFileError("This doesn't look like a MarvelVerse Tracker export file.")

    if data["format_version"] != EXPORT_FORMAT_VERSION:
        raise ComparisonFileError(
            f"This export file (format version {data['format_version']}) isn't compatible with "
            f"this version of the app (format version {EXPORT_FORMAT_VERSION})."
        )

    return data


def compare_with_friend_export(export_path: Path) -> ComparisonResult:
    """Reads `export_path` (a file produced by another install's
    "Export My Data") and compares it against your own current watch
    data. Raises ComparisonFileError for anything that isn't a valid,
    compatible export -- never silently produces a nonsense comparison
    from a malformed file."""
    friend_data = _load_friend_export(export_path)
    friend_projects: dict[str, dict] = friend_data.get("projects", {})

    with session_scope() as session:
        all_projects = session.scalars(select(Project)).all()
        my_data_by_slug: dict[str, UserProjectData] = {
            row.project.slug: row
            for row in session.scalars(
                select(UserProjectData).options(joinedload(UserProjectData.project))
            ).all()
        }

        both_watched = []
        only_me_watched = []
        only_friend_watched = []
        neither_watched_count = 0

        for project in all_projects:
            my_row = my_data_by_slug.get(project.slug)
            my_watched = bool(my_row and my_row.watched)
            my_rating = my_row.rating if my_row else None

            friend_entry = friend_projects.get(project.slug)
            friend_watched = bool(friend_entry and friend_entry.get("watched"))
            friend_rating = friend_entry.get("rating") if friend_entry else None

            if not my_watched and not friend_watched:
                neither_watched_count += 1
                continue

            item = ComparisonItem(
                slug=project.slug,
                title=project.title,
                my_rating=my_rating,
                friend_rating=friend_rating,
            )
            if my_watched and friend_watched:
                both_watched.append(item)
            elif my_watched:
                only_me_watched.append(item)
            else:
                only_friend_watched.append(item)

    return ComparisonResult(
        both_watched=tuple(sorted(both_watched, key=lambda i: i.title)),
        only_me_watched=tuple(sorted(only_me_watched, key=lambda i: i.title)),
        only_friend_watched=tuple(sorted(only_friend_watched, key=lambda i: i.title)),
        neither_watched_count=neither_watched_count,
    )
