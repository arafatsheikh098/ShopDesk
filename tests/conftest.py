"""Pytest fixtures.

We use a fresh SQLite database for each test session. Postgres is used in CI
and in the dedicated M3 concurrent-decrement test.
"""
from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlmodel import Session, SQLModel

# Force test settings before importing the app.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-1234567890-abcdef")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app import db as app_db  # noqa: E402
from app.config import reset_settings_cache  # noqa: E402


@pytest.fixture
def engine():
    """An in-memory SQLite engine shared across the connection (StaticPool)."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    SQLModel.metadata.create_all(eng)
    app_db.set_engine(eng)
    yield eng
    app_db.set_engine(None)


@pytest.fixture
def session(engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(engine) -> Iterator[TestClient]:
    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def tmp_db_path(tmp_path):
    return tmp_path / "shopdesk.db"
