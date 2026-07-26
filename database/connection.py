from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, scoped_session, sessionmaker

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_session_factory: scoped_session | None = None


def init_engine(database_file: Path, *, echo: bool = False) -> Engine:
    """Create (or recreate) the SQLite engine bound to ``database_file``.

    Enables foreign key enforcement and WAL journal mode on every new
    connection, since SQLite does not turn these on by default.
    """
    global _engine, _session_factory

    from sqlalchemy import create_engine  # local import keeps module import light

    database_file.parent.mkdir(parents=True, exist_ok=True)

    _engine = create_engine(
        f"sqlite:///{database_file}",
        echo=echo,
        future=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    _session_factory = scoped_session(
        sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, future=True)
    )

    logger.info("Database engine initialized at %s", database_file)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database engine has not been initialized; call init_engine() first.")
    return _engine


def get_session() -> Session:
    if _session_factory is None:
        raise RuntimeError("Database engine has not been initialized; call init_engine() first.")
    return _session_factory()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope for a series of operations.

    Commits on success, rolls back on any exception, and always closes
    the session afterward.
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engine() -> None:
    """Dispose of the current engine's connection pool. Mainly useful in tests."""
    global _engine, _session_factory
    if _session_factory is not None:
        _session_factory.remove()
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
