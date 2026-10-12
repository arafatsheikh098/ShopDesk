"""Database engine and session management."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings


def _make_engine() -> Engine:
    settings = get_settings()
    url = settings.database_url
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args, future=True)


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def set_engine(engine: Engine | None) -> None:
    """Override the engine (used in tests). Pass None to reset."""
    global _engine
    _engine = engine


def create_db_and_tables() -> None:
    """Create all tables. Used at startup and in tests."""
    # Import models so SQLModel.metadata is populated.
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
