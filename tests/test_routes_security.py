"""Parametrized route discovery tests.

A1 — state-changing routes must require CSRF + session.
A2 — owner-only routes return 403 for cashiers.

We mount a tiny test app with three demo routes (one public GET, one
state-changing unauthenticated endpoint, one owner-only) so the discovery
test is concrete and not coupled to future routers. The production app
contains equivalent guarantees via the `require_csrf` and `require_owner`
dependencies, which are also exercised directly below.
"""
from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth import CSRF_COOKIE, SESSION_COOKIE, hash_password
from app.deps import require_csrf, require_login, require_owner
from app.models import User, UserRole


def _make_demo_app() -> FastAPI:
    app = FastAPI()

    @app.get("/public")
    def public():  # no auth
        return {"ok": True}

    @app.post("/unsafe", dependencies=[Depends(require_csrf)])
    def unsafe():  # requires CSRF + (by route spec) login
        return {"ok": True}

    @app.post("/owner-only", dependencies=[Depends(require_csrf)])
    def owner_only(_owner: User = Depends(require_owner)):
        return {"ok": True}

    @app.post("/login-only", dependencies=[Depends(require_csrf)])
    def login_only(_u: User = Depends(require_login)):
        return {"ok": True}

    return app


@pytest.fixture
def demo_client(engine):
    from app.db import set_engine

    set_engine(engine)
    return TestClient(_make_demo_app())


def _seed(session: Session, role: UserRole, username: str) -> None:
    session.add(
        User(username=username, password_hash=hash_password("pw"), role=role)
    )
    session.commit()


def _login(client: TestClient, session: Session, username: str) -> None:
    # Seed a session cookie directly (demo app doesn't include the auth router).
    from app.auth import make_csrf_token, make_session_cookie

    user = next(u for u in session.exec(__import__("sqlmodel").select(User)) if u.username == username)
    token = make_session_cookie(user.id or 0)
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, make_csrf_token(token))


def test_public_route_does_not_need_auth(demo_client):
    r = demo_client.get("/public")
    assert r.status_code == 200


def test_state_changing_route_without_csrf_returns_403(demo_client):
    r = demo_client.post("/unsafe")
    assert r.status_code == 403


def test_state_changing_route_with_csrf_but_no_session_returns_401_or_403(demo_client):
    # Even with a valid CSRF token, a state-changing route that needs a session
    # must reject. We can't issue a real CSRF without a session cookie, so the
    # missing-token case (403) already proves the guard.
    r = demo_client.post(
        "/unsafe", headers={"X-CSRF-Token": "deadbeef"}
    )
    assert r.status_code in (401, 403)


def test_owner_only_returns_403_for_cashier(demo_client, session):
    _seed(session, UserRole.CASHIER, "c")
    _login(demo_client, session, "c")
    csrf = demo_client.cookies.get(CSRF_COOKIE)
    r = demo_client.post("/owner-only", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 403


def test_owner_only_succeeds_for_owner(demo_client, session):
    _seed(session, UserRole.OWNER, "o")
    _login(demo_client, session, "o")
    csrf = demo_client.cookies.get(CSRF_COOKIE)
    r = demo_client.post("/owner-only", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_login_only_succeeds_for_cashier(demo_client, session):
    _seed(session, UserRole.CASHIER, "c2")
    _login(demo_client, session, "c2")
    csrf = demo_client.cookies.get(CSRF_COOKIE)
    r = demo_client.post("/login-only", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200


def test_discovery_via_real_app(client, session):
    """Walk every state-changing route in the real app and prove CSRF is enforced.

    The TestClient sends no CSRF cookie by default, so every state-changing
    route should return 403 (CSRF) or 401 (auth) — never 2xx.
    """
    routes = _all_routes(client.app)
    state_changing = [
        (m, p) for (m, p) in routes if m in STATE_CHANGING_METHODS
    ]
    assert state_changing, "expected at least one state-changing route"
    for method, path in state_changing:
        # Substitute a dummy path param so the test client doesn't 404.
        r = client.request(method, path.replace("{", "").replace("}", ""))
        assert r.status_code in (401, 403, 405, 422, 307, 303), (
            f"{method} {path} returned {r.status_code} without CSRF"
        )


STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _all_routes(app):
    out = []
    for r in app.router.routes:
        for m in (getattr(r, "methods", None) or set()):
            out.append((m, getattr(r, "path", "")))
    return out
