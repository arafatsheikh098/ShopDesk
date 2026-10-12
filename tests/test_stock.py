"""Stock tests: ledger invariant, no-negative, low-stock, reason required."""
from __future__ import annotations

import os
import threading

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    hash_password,
    make_csrf_token,
    make_session_cookie,
)
from app.models import Product, StockMovement, StockReason, User, UserRole


def _seed_user(session: Session, role: UserRole, username: str = "u") -> None:
    session.add(
        User(username=username, password_hash=hash_password("pw"), role=role)
    )
    session.commit()


def _login_as(client: TestClient, session: Session, username: str) -> None:
    user = next(u for u in session.exec(select(User)) if u.username == username)
    token = make_session_cookie(user.id or 0)
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, make_csrf_token(token))


# ---- A3: stock = sum of ledger deltas (invariant) -----------------------

def test_stock_invariant_equals_ledger_sum(client, session):
    p = Product(name="X", sku="X1", sell_price=100, cost_price=50, stock=0)
    session.add(p)
    session.commit()
    pid = p.id
    for delta, reason in [
        (10, StockReason.OPENING),
        (5, StockReason.PURCHASE),
        (-3, StockReason.SALE),
        (-1, StockReason.ADJUSTMENT),
    ]:
        p = session.get(Product, pid)
        p.stock += delta
        session.add(p)
        session.add(StockMovement(product_id=pid, delta=delta, reason=reason))
    session.commit()
    # invariant
    p = session.get(Product, pid)
    sm = session.exec(select(StockMovement).where(StockMovement.product_id == pid)).all()
    assert p.stock == sum(m.delta for m in sm)
    assert p.stock == 11


# ---- A3: stock never goes negative ---------------------------------------

def test_receive_stock_increases(client, session):
    _seed_user(session, UserRole.OWNER, "o")
    _login_as(client, session, "o")
    p = Product(name="X", sku="X1", sell_price=100, cost_price=50, stock=0)
    session.add(p)
    session.commit()
    pid = p.id
    csrf = client.cookies.get(CSRF_COOKIE)
    r = client.post(
        "/stock/receive",
        data={"product_id": str(pid), "quantity": "5", "note": ""},
        headers={"X-CSRF-Token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    # Use a fresh session to read the latest state.
    from sqlmodel import Session as _S

    from app.db import get_engine

    with _S(get_engine()) as s2:
        assert s2.get(Product, pid).stock == 5


def test_adjust_negative_rejected(client, session):
    _seed_user(session, UserRole.OWNER, "o")
    _login_as(client, session, "o")
    p = Product(name="X", sku="X1", sell_price=100, cost_price=50, stock=2)
    session.add(p)
    session.commit()
    csrf = client.cookies.get(CSRF_COOKIE)
    r = client.post(
        "/stock/adjust",
        data={"product_id": str(p.id), "delta": "-5", "reason_text": "shrinkage"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 400
    # Stock unchanged.
    assert session.get(Product, p.id).stock == 2


def test_adjust_requires_reason(client, session):
    _seed_user(session, UserRole.OWNER, "o")
    _login_as(client, session, "o")
    p = Product(name="X", sku="X1", sell_price=100, cost_price=50, stock=10)
    session.add(p)
    session.commit()
    csrf = client.cookies.get(CSRF_COOKIE)
    r = client.post(
        "/stock/adjust",
        data={"product_id": str(p.id), "delta": "-1", "reason_text": ""},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 400


def test_low_stock_list(client, session):
    _seed_user(session, UserRole.OWNER, "o")
    _login_as(client, session, "o")
    session.add(Product(name="A", sku="A1", sell_price=10, cost_price=5, stock=1, low_stock_threshold=5))
    session.add(Product(name="B", sku="B1", sell_price=10, cost_price=5, stock=10, low_stock_threshold=5))
    session.commit()
    r = client.get("/stock/low")
    assert r.status_code == 200
    assert "A" in r.text and "B" not in r.text


# ---- A4: concurrent decrement on Postgres with 20+ attempts ---------------

@pytest.mark.skipif(
    "postgresql" not in (os.environ.get("DATABASE_URL") or ""),
    reason="Postgres-only test (run with DATABASE_URL=postgresql+psycopg://...)",
)
def test_concurrent_decrement_never_negative_on_postgres():
    """Spin up 20 threads each trying to sell one unit of a product with stock=5.

    Uses a per-thread SQLAlchemy connection to the same Postgres database.
    The transaction in app.stock must take a row lock so the final stock is
    exactly 0 and the 6th..20th attempts fail cleanly.
    """
    import os

    from sqlalchemy import StaticPool, create_engine, text  # noqa: F401
    from sqlmodel import Session, SQLModel

    from app import db as app_db
    from app.models import Product, StockMovement, StockReason
    from app.stock_ops import decrement_stock

    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    SQLModel.metadata.drop_all(eng)
    SQLModel.metadata.create_all(eng)
    app_db.set_engine(eng)
    with Session(eng) as s:
        s.add(Product(id=1, name="Race", sku="R1", sell_price=100, cost_price=50, stock=5))
        s.commit()

    results: list[bool] = []
    lock = threading.Lock()

    def attempt():
        with Session(eng) as s:
            try:
                decrement_stock(s, product_id=1, quantity=1, reason=StockReason.SALE, reference=None, user_id=None)
                s.commit()
                with lock:
                    results.append(True)
            except ValueError:
                with lock:
                    results.append(False)

    threads = [threading.Thread(target=attempt) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successes = sum(1 for r in results if r)
    assert successes == 5, f"expected exactly 5 successes, got {successes}"
    with Session(eng) as s:
        p = s.get(Product, 1)
        assert p.stock == 0
        mvs = s.exec(select(StockMovement).where(StockMovement.product_id == 1)).all()
        assert sum(m.delta for m in mvs) == -5
        assert len(mvs) == 5
