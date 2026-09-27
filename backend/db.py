"""SQLAlchemy engine + session wiring.

Kept deliberately thin: an engine, a ``SessionLocal`` factory, a declarative
``Base``, and an ``init_db`` that creates tables. SQLite needs
``check_same_thread=False`` because FastAPI serves requests across threads.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import Settings, get_settings


class Base(DeclarativeBase):
    """Declarative base for every ORM model in :mod:`backend.models`."""


def make_engine(settings: Settings | None = None):
    settings = settings or get_settings()
    connect_args = {}
    if settings.is_sqlite:
        # FastAPI hands requests to a threadpool; SQLite guards against that by
        # default. We manage sessions per-call, so relaxing the check is safe.
        connect_args["check_same_thread"] = False
    return create_engine(
        settings.database_url,
        connect_args=connect_args,
        future=True,
    )


# Module-level engine/session for the app. Tests build their own in-memory
# engine and override the FastAPI dependency, so this is never a hard singleton.
engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(bind=None) -> None:
    """Create all tables. Import models first so they register on ``Base``."""

    from backend import models  # noqa: F401  (populates Base.metadata)
    from backend.auth import models as auth_models  # noqa: F401  (users table)

    Base.metadata.create_all(bind or engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yields a session and always closes it."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session for non-request code (seeding, agents, tests)."""

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
