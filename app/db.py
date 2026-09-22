"""Database engine, session factory and the declarative base.

The engine is created once at import time from `settings.database_url`. Tests
build their own in-memory engine instead (see `tests/conftest.py`), which is why
nothing outside this module is allowed to reach for a global session.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def create_db_engine(database_url: str) -> Engine:
    """Create an engine with the connect args SQLite needs under FastAPI."""
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, future=True, connect_args=connect_args)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """SQLite ignores foreign keys unless asked, per connection, to enforce them."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    except Exception:  # pragma: no cover - non-SQLite backends
        # Not fatal: other backends enforce foreign keys without the pragma. Logged
        # rather than swallowed, so a genuinely unenforced constraint is visible.
        logger.debug("Could not enable SQLite foreign keys", exc_info=True)
    finally:
        cursor.close()


engine = create_db_engine(settings.database_url)
SessionFactory = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def create_all(target_engine: Engine | None = None) -> None:
    """Create or upgrade the local schema."""
    from . import models  # noqa: F401  (import registers the mappers)
    from .migrations import run_migrations

    selected_engine = target_engine or engine
    Base.metadata.create_all(selected_engine)
    run_migrations(selected_engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    with SessionFactory() as session:
        yield session
