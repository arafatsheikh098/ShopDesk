"""Health endpoint + production SECRET_KEY refusal."""
from __future__ import annotations

import subprocess
import sys

import pytest

from app.config import DEFAULT_SECRET_KEY


def test_health(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_production_refuses_default_secret() -> None:
    """In production, create_app must SystemExit(2) when SECRET_KEY is default.

    We exercise the factory in a subprocess so it doesn't poison this process
    (the module-level `app = create_app()` would otherwise be built before
    the test can swap env vars).
    """
    code = (
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import os; os.environ['APP_ENV']='production';"
                f" os.environ['SECRET_KEY']={DEFAULT_SECRET_KEY!r};"
                " from app.main import create_app; create_app()",
            ],
            capture_output=True,
            text=True,
        )
        .returncode
    )
    assert code == 2


def test_production_works_with_real_secret() -> None:
    """In production with a real SECRET_KEY, the app boots cleanly."""
    code = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; os.environ['APP_ENV']='production';"
            " os.environ['SECRET_KEY']='a-real-long-secret-1234567890-abcdef';"
            " from app.main import create_app; a = create_app();"
            " assert a.title == 'ShopDesk'",
        ],
        capture_output=True,
        text=True,
    )
    assert code.returncode == 0, code.stderr
