"""Database package: engine/session management, migrations, and seeding.

The public entry point is :func:`init_database`, which the application
controller calls once at startup. It wires up the SQLAlchemy engine, brings
the schema up to date via Alembic, and seeds canonical reference data
(universes, franchises, genres, achievements) on a fresh install.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from alembic import command
from alembic.config import Config

from database.connection import (
    dispose_engine,
    get_engine,
    get_session,
    init_engine,
    session_scope,
)
from resource_paths import resource_root

logger = logging.getLogger(__name__)

PROJECT_ROOT = resource_root()
MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
# The catalog this app ships with -- bundled into the packaged .exe (see
# packaging/MarvelVerseTracker.spec's added_files) so a first-ever run
# has the real, current catalog to work with, not an empty one.
BUNDLED_CATALOG_DATABASE = PROJECT_ROOT / "data" / "marvelverse.db"


def _alembic_config(database_file: Path) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_file}")
    return config


def run_migrations(database_file: Path) -> None:
    """Bring the SQLite database at ``database_file`` up to the latest
    Alembic revision, creating it first if it doesn't exist yet."""
    logger.info("Running database migrations")
    config = _alembic_config(database_file)
    command.upgrade(config, "head")
    logger.info("Database migrations complete")


def _ensure_catalog_database_exists(database_file: Path) -> None:
    """If `database_file` (the user's actual, persistent database --
    e.g. %LOCALAPPDATA%\\MarvelVerseTracker\\data\\marvelverse.db for a
    packaged install) doesn't exist yet, seeds it by copying the
    catalog this build actually ships with, rather than leaving it to
    be created empty by migrations alone.

    Without this step, a packaged .exe had no way to ever get the real
    movie/show catalog into a fresh installation at all -- migrations
    only create empty tables, and seed_all() (see init_database below)
    only seeds reference data (universes, franchises, genres,
    achievements), never the catalog itself.

    Only acts when `database_file` doesn't exist yet -- an existing
    install's database (with the user's own watch history, ratings,
    achievements progress, etc.) is never touched or overwritten by
    this, only ever created fresh from the bundled copy the first time.

    Running from source, BUNDLED_CATALOG_DATABASE and `database_file`
    normally resolve to the exact same path already (both come from the
    project's own "data" folder) -- this is a correct no-op in that
    case, not an error, so it's checked for explicitly rather than
    attempting (and failing) to copy a file onto itself.
    """
    if database_file.exists():
        return
    if not BUNDLED_CATALOG_DATABASE.exists():
        logger.warning(
            "No bundled catalog database found at %s -- starting with an empty catalog.",
            BUNDLED_CATALOG_DATABASE,
        )
        return
    if BUNDLED_CATALOG_DATABASE.resolve() == database_file.resolve():
        return

    logger.info("First run: seeding catalog database from %s", BUNDLED_CATALOG_DATABASE)
    database_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BUNDLED_CATALOG_DATABASE, database_file)


def sync_new_catalog_projects(target_database_file: Path) -> int:
    """Adds any projects from the bundled catalog (BUNDLED_CATALOG_DATABASE)
    that don't already exist -- matched by slug -- into the database at
    `target_database_file`, leaving every existing project and every
    piece of personal data (watch history, ratings, achievements,
    episodes, collections, ...) completely untouched.

    This is the "catch up an existing install" counterpart to
    _ensure_catalog_database_exists(): that one only ever helps a
    genuinely fresh install (no database file yet); this one is for
    someone who already has an install with real personal data, whose
    database predates some catalog additions, and who wants those new
    additions without starting over.

    Returns the number of new projects added. A no-op (returning 0) if
    there's no bundled catalog to read from, or if the bundled catalog
    and the target happen to be the exact same file (running from
    source, where there's nothing to "catch up" from by definition).
    """
    if not BUNDLED_CATALOG_DATABASE.exists():
        return 0
    if BUNDLED_CATALOG_DATABASE.resolve() == target_database_file.resolve():
        return 0

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import joinedload, sessionmaker

    from models import Franchise, Genre, Person, Project, ProjectCast, ProjectCrew, Tag, Universe

    source_engine = create_engine(f"sqlite:///{BUNDLED_CATALOG_DATABASE}")
    SourceSession = sessionmaker(bind=source_engine)
    source_session = SourceSession()

    added_count = 0
    try:
        source_projects = (
            source_session.query(Project)
            .options(
                joinedload(Project.genres),
                joinedload(Project.tags),
                joinedload(Project.universe),
                joinedload(Project.franchise),
                joinedload(Project.cast).joinedload(ProjectCast.person),
                joinedload(Project.crew).joinedload(ProjectCrew.person),
            )
            .all()
        )

        with session_scope() as target_session:
            existing_slugs = {row[0] for row in target_session.execute(select(Project.slug))}

            for source_project in source_projects:
                if source_project.slug in existing_slugs:
                    continue

                target_universe_id = None
                if source_project.universe is not None:
                    target_universe = (
                        target_session.query(Universe).filter_by(slug=source_project.universe.slug).first()
                    )
                    target_universe_id = target_universe.id if target_universe else None

                target_franchise_id = None
                if source_project.franchise is not None:
                    target_franchise = (
                        target_session.query(Franchise).filter_by(slug=source_project.franchise.slug).first()
                    )
                    target_franchise_id = target_franchise.id if target_franchise else None

                new_project = Project(
                    title=source_project.title,
                    slug=source_project.slug,
                    project_type=source_project.project_type,
                    status=source_project.status,
                    universe_id=target_universe_id,
                    franchise_id=target_franchise_id,
                    release_date=source_project.release_date,
                    runtime_minutes=source_project.runtime_minutes,
                    studio=source_project.studio,
                    synopsis=source_project.synopsis,
                    in_universe_date=source_project.in_universe_date,
                    season_count=source_project.season_count,
                    episode_count=source_project.episode_count,
                    cancelled_date=source_project.cancelled_date,
                    next_season_release_date=source_project.next_season_release_date,
                    production_start_date=source_project.production_start_date,
                    poster_path=source_project.poster_path,
                    background_path=source_project.background_path,
                    trailer_url=source_project.trailer_url,
                    saga=source_project.saga,
                    phase=source_project.phase,
                    chronological_order=source_project.chronological_order,
                    tmdb_id=source_project.tmdb_id,
                    imdb_id=source_project.imdb_id,
                )

                for source_genre in source_project.genres:
                    target_genre = target_session.query(Genre).filter_by(name=source_genre.name).first()
                    if target_genre is not None:
                        new_project.genres.append(target_genre)

                for source_tag in source_project.tags:
                    target_tag = target_session.query(Tag).filter_by(slug=source_tag.slug).first()
                    if target_tag is not None:
                        new_project.tags.append(target_tag)

                target_session.add(new_project)
                target_session.flush()

                for source_cast in source_project.cast:
                    person = target_session.query(Person).filter_by(slug=source_cast.person.slug).first()
                    if person is None:
                        person = Person(
                            name=source_cast.person.name,
                            slug=source_cast.person.slug,
                            photo_path=source_cast.person.photo_path,
                            bio=source_cast.person.bio,
                        )
                        target_session.add(person)
                        target_session.flush()
                    target_session.add(
                        ProjectCast(
                            project_id=new_project.id,
                            person_id=person.id,
                            character_name=source_cast.character_name,
                            billing_order=source_cast.billing_order,
                        )
                    )

                for source_crew in source_project.crew:
                    person = target_session.query(Person).filter_by(slug=source_crew.person.slug).first()
                    if person is None:
                        person = Person(
                            name=source_crew.person.name,
                            slug=source_crew.person.slug,
                            photo_path=source_crew.person.photo_path,
                            bio=source_crew.person.bio,
                        )
                        target_session.add(person)
                        target_session.flush()
                    target_session.add(
                        ProjectCrew(project_id=new_project.id, person_id=person.id, role=source_crew.role)
                    )

                existing_slugs.add(source_project.slug)
                added_count += 1
    finally:
        source_session.close()
        source_engine.dispose()

    if added_count:
        logger.info("Added %d new catalog project(s) to an existing install", added_count)
    return added_count


def init_database(
    database_file: Path, *, echo: bool = False, seed: bool = True, copy_bundled_catalog: bool = False
) -> None:
    """Full startup sequence: engine, migrations, and (optionally) seed data.

    Safe to call every time the app starts — migrations are idempotent and
    seeding only inserts rows that don't already exist.

    `copy_bundled_catalog` defaults to False deliberately: the real
    application startup path (controllers.application_controller) is
    the only caller that should ever pass True. Every test in this
    entire suite calls this with a fresh tmp_path expecting to start
    from an empty catalog and build its own test data on top -- making
    this default to on would have silently copied the real 196-project
    catalog into every single one of those tests' databases instead.

    When True, this covers both cases: a genuinely fresh install (no
    database file yet) gets the whole bundled catalog copied in, and an
    *existing* install (with real personal data already in it) gets any
    newly-added catalog projects synced in on top -- see
    _ensure_catalog_database_exists and sync_new_catalog_projects
    respectively. Either way, existing projects and all personal data
    (watch history, ratings, achievements, episodes, collections, ...)
    are never touched.
    """
    database_existed_already = database_file.exists()
    if copy_bundled_catalog:
        _ensure_catalog_database_exists(database_file)

    init_engine(database_file, echo=echo)
    run_migrations(database_file)

    if seed:
        from database.seed.reference_data import seed_all

        with session_scope() as session:
            seed_all(session)

    if copy_bundled_catalog and database_existed_already:
        sync_new_catalog_projects(database_file)


__all__ = [
    "init_engine",
    "get_engine",
    "get_session",
    "session_scope",
    "dispose_engine",
    "run_migrations",
    "init_database",
    "sync_new_catalog_projects",
    "PROJECT_ROOT",
    "MIGRATIONS_DIR",
    "BUNDLED_CATALOG_DATABASE",
]
