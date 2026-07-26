"""Database package: engine/session management, migrations, and seeding.

The public entry point is :func:`init_database`, which the application
controller calls once at startup. It wires up the SQLAlchemy engine, brings
the schema up to date via Alembic, and seeds canonical reference data
(universes, franchises, genres, achievements) on a fresh install.
"""

from __future__ import annotations

import logging
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


def init_database(database_file: Path, *, echo: bool = False, seed: bool = True) -> None:
    """Full startup sequence: engine, migrations, and (optionally) seed data.

    Safe to call every time the app starts — migrations are idempotent and
    seeding only inserts rows that don't already exist.
    """
    init_engine(database_file, echo=echo)
    run_migrations(database_file)

    if seed:
        from database.seed.reference_data import seed_all

        with session_scope() as session:
            seed_all(session)


__all__ = [
    "init_engine",
    "get_engine",
    "get_session",
    "session_scope",
    "dispose_engine",
    "run_migrations",
    "init_database",
    "PROJECT_ROOT",
    "MIGRATIONS_DIR",
]
