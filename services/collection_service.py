"""User-curated Collections -- manually grouped, manually ordered sets of
projects (e.g. "Infinity Saga Ranked", "Weekend Marathon"), distinct from
the canonical Universe/Franchise groupings synced from TMDB.

This only covers manual collections. ``Collection.is_smart`` exists in the
schema for a future "auto-computed from a saved filter" mode (e.g. "all
unwatched Phase 4 projects"), but that's a materially different feature --
it needs a persisted filter definition and a live re-evaluation engine --
and isn't implemented here. Every collection this module creates has
``is_smart=False``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from database import session_scope
from models import Collection, CollectionProject, Project, ProjectStatus, ProjectType

logger = logging.getLogger(__name__)


class CollectionNotFoundError(Exception):
    """Raised when a collection_id doesn't correspond to any row."""


class ProjectAlreadyInCollectionError(Exception):
    """Raised by add_project_to_collection() for a project that's already
    a member -- distinct from a generic error so the UI can show a
    friendly "already in this collection" message rather than a raw
    failure."""


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "collection"


def _unique_slug(session, base_slug: str, *, exclude_id: int | None = None) -> str:
    """Appends a numeric suffix if `base_slug` is already taken by a
    different collection -- same shape as backup_service's
    suffix-on-collision handling, since collections have no natural
    external id (like TMDB's) to disambiguate with instead."""
    slug = base_slug
    suffix = 2
    while True:
        stmt = select(Collection.id).where(Collection.slug == slug)
        if exclude_id is not None:
            stmt = stmt.where(Collection.id != exclude_id)
        if session.scalar(stmt) is None:
            return slug
        slug = f"{base_slug}-{suffix}"
        suffix += 1


@dataclass(frozen=True)
class CollectionSummary:
    """A flat, detached-safe read model for one row in the Collections
    list -- everything needed to render a collection card without its
    full project list."""

    id: int
    name: str
    slug: str
    description: str | None
    cover_image_path: str | None
    is_smart: bool
    project_count: int


@dataclass(frozen=True)
class CollectionProjectItem:
    """One project within a collection, in manual-order position. Same
    shape as services.project_service.ProjectListItem plus ``position``,
    so collections_view can reuse the same rendering conventions
    (poster, type/status/rating) the Library already uses."""

    id: int
    title: str
    slug: str
    project_type: ProjectType
    status: ProjectStatus
    release_date: date | None
    poster_path: str | None
    watched: bool
    favorite: bool
    rating: float | None
    position: int


@dataclass(frozen=True)
class CollectionDetail:
    """Full detail for one collection: its own fields plus every member
    project in manual order."""

    id: int
    name: str
    slug: str
    description: str | None
    is_smart: bool
    projects: tuple[CollectionProjectItem, ...]


def _to_summary(collection: Collection) -> CollectionSummary:
    return CollectionSummary(
        id=collection.id,
        name=collection.name,
        slug=collection.slug,
        description=collection.description,
        cover_image_path=collection.cover_image_path,
        is_smart=collection.is_smart,
        project_count=len(collection.project_links),
    )


def list_collections() -> tuple[CollectionSummary, ...]:
    """Every collection, alphabetical by name. Cheap enough to call every
    time the Collections page opens or changes; owns its own session
    scope like everything else in the services layer."""
    with session_scope() as session:
        collections = session.scalars(
            select(Collection)
            .options(selectinload(Collection.project_links))
            .order_by(Collection.name)
        ).all()
        return tuple(_to_summary(c) for c in collections)


def get_collection_detail(collection_id: int) -> CollectionDetail | None:
    """Full detail for one collection, or None if it no longer exists
    (e.g. deleted from another window/process since the list was last
    loaded) -- callers should treat that the same as "not found", not an
    error."""
    with session_scope() as session:
        collection = session.get(
            Collection,
            collection_id,
            options=[
                selectinload(Collection.project_links)
                .joinedload(CollectionProject.project)
                .options(joinedload(Project.user_data)),
            ],
        )
        if collection is None:
            return None

        projects = tuple(
            CollectionProjectItem(
                id=link.project.id,
                title=link.project.title,
                slug=link.project.slug,
                project_type=link.project.project_type,
                status=link.project.status,
                release_date=link.project.release_date,
                poster_path=link.project.poster_path,
                watched=link.project.user_data.watched if link.project.user_data else False,
                favorite=link.project.user_data.favorite if link.project.user_data else False,
                rating=link.project.user_data.rating if link.project.user_data else None,
                position=link.position,
            )
            for link in collection.project_links
        )
        return CollectionDetail(
            id=collection.id,
            name=collection.name,
            slug=collection.slug,
            description=collection.description,
            is_smart=collection.is_smart,
            projects=projects,
        )


def create_collection(name: str, description: str | None = None) -> CollectionSummary:
    name = name.strip()
    if not name:
        raise ValueError("Collection name cannot be blank.")

    with session_scope() as session:
        slug = _unique_slug(session, _slugify(name))
        collection = Collection(
            name=name,
            slug=slug,
            description=(description or "").strip() or None,
            is_smart=False,
        )
        session.add(collection)
        session.flush()
        logger.info("Created collection %r (id=%s)", name, collection.id)
        return _to_summary(collection)


def rename_collection(collection_id: int, name: str, description: str | None = None) -> CollectionSummary:
    name = name.strip()
    if not name:
        raise ValueError("Collection name cannot be blank.")

    with session_scope() as session:
        collection = session.get(
            Collection, collection_id, options=[selectinload(Collection.project_links)]
        )
        if collection is None:
            raise CollectionNotFoundError(f"Collection id={collection_id} not found")

        collection.name = name
        collection.description = (description or "").strip() or None
        if _slugify(name) != collection.slug:
            collection.slug = _unique_slug(session, _slugify(name), exclude_id=collection_id)
        session.flush()
        return _to_summary(collection)


def delete_collection(collection_id: int) -> None:
    """Deletes the collection and its membership links (CollectionProject
    rows cascade via the ORM relationship's cascade="all, delete-orphan").
    Never touches the member Project rows themselves -- a collection is
    just a curated view over the catalog, not ownership of it."""
    with session_scope() as session:
        collection = session.get(Collection, collection_id)
        if collection is None:
            return
        session.delete(collection)
        logger.info("Deleted collection id=%s", collection_id)


def add_project_to_collection(collection_id: int, project_id: int) -> CollectionDetail:
    with session_scope() as session:
        collection = session.get(
            Collection, collection_id, options=[selectinload(Collection.project_links)]
        )
        if collection is None:
            raise CollectionNotFoundError(f"Collection id={collection_id} not found")

        project = session.get(Project, project_id)
        if project is None:
            raise ValueError(f"Project id={project_id} not found")

        if any(link.project_id == project_id for link in collection.project_links):
            raise ProjectAlreadyInCollectionError(
                f"{project.title!r} is already in {collection.name!r}"
            )

        next_position = max((link.position for link in collection.project_links), default=-1) + 1
        session.add(
            CollectionProject(collection_id=collection_id, project_id=project_id, position=next_position)
        )
        session.flush()
        logger.info("Added project id=%s to collection id=%s", project_id, collection_id)

    return get_collection_detail(collection_id)


def remove_project_from_collection(collection_id: int, project_id: int) -> CollectionDetail:
    with session_scope() as session:
        link = session.scalar(
            select(CollectionProject).where(
                CollectionProject.collection_id == collection_id,
                CollectionProject.project_id == project_id,
            )
        )
        if link is not None:
            session.delete(link)
            session.flush()
            _renumber_positions(session, collection_id)
            logger.info("Removed project id=%s from collection id=%s", project_id, collection_id)

    return get_collection_detail(collection_id)


def move_project(collection_id: int, project_id: int, direction: str) -> CollectionDetail:
    """Swap `project_id` with its immediate neighbor -- direction is
    "up" (earlier/lower position) or "down" (later/higher position).
    A no-op (not an error) if the project is already at that end of the
    list, so a UI can leave both buttons enabled without needing to
    track which end it's showing."""
    if direction not in ("up", "down"):
        raise ValueError(f"direction must be 'up' or 'down', got {direction!r}")

    with session_scope() as session:
        links = list(
            session.scalars(
                select(CollectionProject)
                .where(CollectionProject.collection_id == collection_id)
                .order_by(CollectionProject.position)
            )
        )
        index = next((i for i, link in enumerate(links) if link.project_id == project_id), None)
        if index is None:
            return get_collection_detail(collection_id)

        swap_index = index - 1 if direction == "up" else index + 1
        if not (0 <= swap_index < len(links)):
            return get_collection_detail(collection_id)

        links[index].position, links[swap_index].position = (
            links[swap_index].position,
            links[index].position,
        )
        session.flush()

    return get_collection_detail(collection_id)


def _renumber_positions(session, collection_id: int) -> None:
    """Compacts position values back to a gapless 0..N-1 sequence after a
    removal, so a future add_project_to_collection() call's "append at
    max(position)+1" logic doesn't accumulate gaps forever."""
    links = list(
        session.scalars(
            select(CollectionProject)
            .where(CollectionProject.collection_id == collection_id)
            .order_by(CollectionProject.position)
        )
    )
    for index, link in enumerate(links):
        link.position = index


def get_pickable_projects(exclude_collection_id: int | None = None) -> list[tuple[int, str]]:
    """(id, title) for every project, alphabetical -- populates the
    Collections page's "Add Project" picker. If `exclude_collection_id`
    is given, projects already in that collection are left out, since
    add_project_to_collection() would just reject them anyway."""
    with session_scope() as session:
        stmt = select(Project.id, Project.title).order_by(Project.title)
        if exclude_collection_id is not None:
            already_in = select(CollectionProject.project_id).where(
                CollectionProject.collection_id == exclude_collection_id
            )
            stmt = stmt.where(Project.id.not_in(already_in))
        return [(pid, title) for pid, title in session.execute(stmt).all()]
