"""Offline PWA tests: idempotency, manifest, sw cache flow."""
from __future__ import annotations

import os

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
from app.models import (
    PaymentMethod,
    Product,
    Sale,
    SaleLine,
    SaleStatus,
    StockMovement,
    StockReason,
    User,
    UserRole,
)


def _login_as(client: TestClient, session: Session, username: str) -> None:
    user = next(u for u in session.exec(select(User)) if u.username == username)
    token = make_session_cookie(user.id or 0)
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, make_csrf_token(token))


# ---- A1: same idempotency key twice → one sale, one stock movement ----

def test_same_idempotency_key_twice_returns_same_sale_and_one_movement(client, session):
    session.add(
        User(username="o", password_hash=hash_password("pw"), role=UserRole.OWNER)
    )
    session.commit()
    _login_as(client, session, "o")
    p = Product(name="X", sku="X1", sell_price=100, cost_price=50, stock=10)
    session.add(p)
    session.commit()
    csrf = client.cookies.get(CSRF_COOKIE)
    payload = {
        "idempotency_key": "the-same-key-1",
        "lines": [{"product_id": p.id, "quantity": 2}],
        "payment_method": "cash",
    }
    r1 = client.post("/api/sales", json=payload, headers={"X-CSRF-Token": csrf})
    r2 = client.post("/api/sales", json=payload, headers={"X-CSRF-Token": csrf})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["sale_number"] == r2.json()["sale_number"]
    sales = session.exec(select(Sale)).all()
    assert len(sales) == 1
    mvs = session.exec(
        select(StockMovement).where(StockMovement.product_id == p.id)
    ).all()
    assert len(mvs) == 1
    session.expire_all()
    assert session.get(Product, p.id).stock == 8


# ---- A3: queued sale with insufficient stock → needs-review -----------

def test_needs_review_for_offline_sale_with_insufficient_stock(client, session):
    session.add(
        User(username="o", password_hash=hash_password("pw"), role=UserRole.OWNER)
    )
    session.commit()
    _login_as(client, session, "o")
    p = Product(name="X", sku="X1", sell_price=100, cost_price=50, stock=1)
    session.add(p)
    session.commit()
    csrf = client.cookies.get(CSRF_COOKIE)
    # First a successful sale that drops stock to 0.
    r = client.post(
        "/api/sales",
        json={
            "idempotency_key": "k1",
            "lines": [{"product_id": p.id, "quantity": 1}],
            "payment_method": "cash",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    # Now a sale that needs 1 but stock is 0. The server returns 400.
    r = client.post(
        "/api/sales",
        json={
            "idempotency_key": "k2",
            "lines": [{"product_id": p.id, "quantity": 1}],
            "payment_method": "cash",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 400
    # In real life, the JS would move it to a "needs review" IndexedDB
    # store when the server returns 4xx. Here we just assert the server
    # response is non-2xx and includes enough info for the UI to act.
    assert "insufficient" in r.json()["detail"].lower() or "stock" in r.json()["detail"].lower()
    # And no new sale row, no new ledger row.
    sales = session.exec(select(Sale)).all()
    assert len(sales) == 1


# ---- A5: offline mode never exposes pages other than POS shell + products list

def test_offline_safelist_only_pos(client, session):
    # The SW caches only /pos and /static/*; other HTML pages must NOT be
    # in the precache. We assert the SHELL array only contains safe entries.
    from pathlib import Path

    src = (Path(__file__).parent.parent / "app" / "static" / "sw.js").read_text()
    # Extract the SHELL array literal.
    start = src.find("const SHELL = [")
    assert start != -1, "SHELL constant missing"
    end = src.find("];", start)
    shell_block = src[start:end]
    # Only the POS page and static assets are precached.
    assert "/pos" in shell_block
    assert "/products" not in shell_block
    assert "/reports" not in shell_block
    assert "/stock" not in shell_block


def test_manifest_and_icons_served(client):
    r = client.get("/static/manifest.webmanifest")
    assert r.status_code == 200
    assert "ShopDesk" in r.json()["name"]
    r = client.get("/static/icons/icon-192.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    r = client.get("/static/icons/icon-512.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_sw_served_at_static_path(client):
    r = client.get("/static/sw.js")
    assert r.status_code == 200
    assert "service worker" in r.text.lower() or "addEventListener" in r.text


# ---- A4: new deployment updates the cached app shell safely ---------

def test_sw_version_is_bumped_with_safe_update_flow():
    """The SW uses a VERSION constant; on activation it deletes old caches and
    claims clients. We assert the structure of the SW matches the 'safe
    update' pattern: install + skipWaiting + activate deletes other caches.
    """
    from pathlib import Path

    src = (Path(__file__).parent.parent / "app" / "static" / "sw.js").read_text()
    assert "VERSION" in src
    assert "skipWaiting" in src
    assert "caches.delete" in src
    assert "SKIP_WAITING" in src  # clients can trigger update


# ---- F7.7: client-supplied price that mismatches the server price flags the sale

def test_price_mismatch_flags_sale_for_owner_review(client, session):
    session.add(
        User(username="o", password_hash=hash_password("pw"), role=UserRole.OWNER)
    )
    session.commit()
    _login_as(client, session, "o")
    p = Product(name="X", sku="X1", sell_price=100, cost_price=50, stock=10)
    session.add(p)
    session.commit()
    csrf = client.cookies.get(CSRF_COOKIE)
    # Client sends a different unit_price (as an offline-synced sale would).
    r = client.post(
        "/api/sales",
        json={
            "idempotency_key": "mismatch-1",
            "lines": [{"product_id": p.id, "quantity": 1, "unit_price": 80}],
            "payment_method": "cash",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["price_mismatch_warning"] is True
    # And the sale's line keeps the client price (customer was charged that).
    session.expire_all()
    sale = session.exec(select(Sale).where(Sale.sale_number == body["sale_number"])).first()
    assert sale is not None
    assert sale.price_mismatch_warning is True


def test_no_price_mismatch_when_unit_price_matches(client, session):
    session.add(
        User(username="o", password_hash=hash_password("pw"), role=UserRole.OWNER)
    )
    session.commit()
    _login_as(client, session, "o")
    p = Product(name="X", sku="X1", sell_price=100, cost_price=50, stock=10)
    session.add(p)
    session.commit()
    csrf = client.cookies.get(CSRF_COOKIE)
    # Client sends the same price the server has.
    r = client.post(
        "/api/sales",
        json={
            "idempotency_key": "match-1",
            "lines": [{"product_id": p.id, "quantity": 1, "unit_price": 100}],
            "payment_method": "cash",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    assert r.json()["price_mismatch_warning"] is False
