"""Catalog tests: uniqueness, CSV import, search, cashier cannot see cost."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    hash_password,
    make_csrf_token,
    make_session_cookie,
)
from app.models import Product, User, UserRole


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


# ---- A1: uniqueness -------------------------------------------------------

def test_duplicate_sku_rejected(client, session):
    _seed_user(session, UserRole.OWNER)
    p1 = Product(name="A", sku="X1", sell_price=100, cost_price=50)
    p2 = Product(name="B", sku="X1", sell_price=200, cost_price=80)
    session.add(p1)
    session.add(p2)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_duplicate_barcode_rejected(client, session):
    _seed_user(session, UserRole.OWNER)
    session.add(Product(name="A", sku="X1", barcode="BC1", sell_price=100, cost_price=50))
    session.add(Product(name="B", sku="X2", barcode="BC1", sell_price=200, cost_price=80))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


# ---- A2: CSV import dry-run and commit ------------------------------------

CSV_OK = b"name,sku,barcode,unit,sell_price,cost_price,low_stock_threshold\nApple,AP1,BC1,pcs,1.50,0.50,5\nBanana,BN1,,pcs,2.00,1.00,3\n"
CSV_BAD = b"name,sku,barcode,unit,sell_price,cost_price,low_stock_threshold\n,SKU_NO_NAME,BC,pcs,1.00,0.50,1\nOK,OK2,,pcs,1.00,0.50,1\n"
CSV_MISSING = b"name\nFoo\n"


def test_csv_dry_run_reports_bad_rows(client, session):
    _seed_user(session, UserRole.OWNER, "o")
    _login_as(client, session, "o")
    csrf = client.cookies.get(CSRF_COOKIE)
    r = client.post(
        "/products/import",
        files={"file": ("t.csv", CSV_BAD, "text/csv")},
        data={"confirm": ""},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["would_import"] == 1
    assert len(body["errors"]) == 1
    assert body["errors"][0]["row_number"] == 1  # the empty-name row is the first data row
    # No products were committed
    assert session.exec(select(Product)).first() is None


def test_csv_dry_run_rejects_missing_columns(client, session):
    _seed_user(session, UserRole.OWNER, "o")
    _login_as(client, session, "o")
    csrf = client.cookies.get(CSRF_COOKIE)
    r = client.post(
        "/products/import",
        files={"file": ("t.csv", CSV_MISSING, "text/csv")},
        data={"confirm": ""},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["would_import"] == 0
    assert "missing columns" in body["errors"][0]["errors"][0]


def test_csv_commit_inserts_good_rows(client, session):
    _seed_user(session, UserRole.OWNER, "o")
    _login_as(client, session, "o")
    csrf = client.cookies.get(CSRF_COOKIE)
    r = client.post(
        "/products/import",
        files={"file": ("t.csv", CSV_BAD, "text/csv")},
        data={"confirm": "yes"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is False
    assert body["imported"] == 1
    assert session.exec(select(Product)).one().sku == "OK2"


def test_csv_full_ok_file(client, session):
    _seed_user(session, UserRole.OWNER, "o")
    _login_as(client, session, "o")
    csrf = client.cookies.get(CSRF_COOKIE)
    r = client.post(
        "/products/import",
        files={"file": ("t.csv", CSV_OK, "text/csv")},
        data={"confirm": "yes"},
        headers={"X-CSRF-Token": csrf},
    )
    body = r.json()
    assert body["imported"] == 2
    assert session.exec(select(Product)).all().__len__() == 2


# ---- A4: search by name/SKU/barcode ---------------------------------------

def test_search_by_name_sku_barcode(client, session):
    _seed_user(session, UserRole.CASHIER, "c")
    _login_as(client, session, "c")
    session.add(Product(name="Red Apple", sku="A1", barcode="BC-A", sell_price=100, cost_price=50))
    session.add(Product(name="Banana", sku="B1", barcode="BC-B", sell_price=200, cost_price=80))
    session.commit()
    r = client.get("/products/api/search", params={"q": "Apple"})
    assert r.status_code == 200
    data = r.json()
    assert any(p["sku"] == "A1" for p in data)
    r = client.get("/products/api/search", params={"q": "BC-B"})
    data = r.json()
    assert any(p["sku"] == "B1" for p in data)
    r = client.get("/products/api/search", params={"q": "B1"})
    data = r.json()
    assert any(p["sku"] == "B1" for p in data)


# ---- A5: cashier cannot see cost -----------------------------------------

def test_cashier_cannot_see_cost_in_list_page(client, session):
    _seed_user(session, UserRole.CASHIER, "c")
    _login_as(client, session, "c")
    session.add(Product(name="Apple", sku="A1", sell_price=100, cost_price=50))
    session.commit()
    r = client.get("/products")
    assert r.status_code == 200
    body = r.text
    assert "50" not in body or "cost" not in body.lower()  # cost column header hidden
    assert "Apple" in body


def test_cashier_cannot_see_cost_in_new_page(client, session):
    _seed_user(session, UserRole.CASHIER, "c")
    _login_as(client, session, "c")
    r = client.get("/products/new")
    # Owner-only route: cashier gets 403.
    assert r.status_code == 403


def test_cashier_api_search_omits_cost(client, session):
    _seed_user(session, UserRole.CASHIER, "c")
    _login_as(client, session, "c")
    session.add(Product(name="Apple", sku="A1", sell_price=100, cost_price=50))
    session.commit()
    r = client.get("/products/api/search", params={"q": "Apple"})
    data = r.json()
    assert all("cost_price" not in p for p in data)
