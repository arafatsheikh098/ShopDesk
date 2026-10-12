"""Settings page tests."""
from __future__ import annotations

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
from app.models import Setting, User, UserRole


def _login_as_owner(client: TestClient, session: Session) -> None:
    session.add(
        User(username="o", password_hash=hash_password("pw"), role=UserRole.OWNER)
    )
    session.commit()
    user = next(u for u in session.exec(select(User)))
    token = make_session_cookie(user.id or 0)
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, make_csrf_token(token))


def test_settings_page_owner_can_save(client: TestClient, session: Session):
    _login_as_owner(client, session)
    r = client.get("/settings")
    assert r.status_code == 200
    assert "Shop name" in r.text
    # Save.
    csrf = client.cookies.get(CSRF_COOKIE)
    r = client.post(
        "/settings",
        data={
            "shop_name": "Acme Grocery",
            "shop_address": "1 Main St",
            "shop_phone": "555-0100",
            "currency_symbol": "$",
            "shop_timezone": "UTC",
            "invoice_footer": "Thanks!",
            "_csrf": csrf,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code in (200, 303)
    rows = session.exec(select(Setting)).all()
    by_key = {r.key: r.value for r in rows}
    assert by_key["shop_name"] == "Acme Grocery"
    assert by_key["shop_address"] == "1 Main St"
    assert by_key["currency_symbol"] == "$"
    assert by_key["shop_timezone"] == "UTC"
    assert by_key["invoice_footer"] == "Thanks!"


def test_settings_page_cashier_forbidden(client: TestClient, session: Session):
    session.add(
        User(username="c", password_hash=hash_password("pw"), role=UserRole.CASHIER)
    )
    session.commit()
    user = next(u for u in session.exec(select(User)))
    token = make_session_cookie(user.id or 0)
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, make_csrf_token(token))
    r = client.get("/settings")
    assert r.status_code == 403


def test_settings_db_overrides_win_over_env_defaults(client: TestClient, session: Session):
    _login_as_owner(client, session)
    csrf = client.cookies.get(CSRF_COOKIE)
    client.post(
        "/settings",
        data={
            "shop_name": "FromDB",
            "shop_address": "",
            "shop_phone": "",
            "currency_symbol": "€",
            "shop_timezone": "Asia/Dhaka",
            "invoice_footer": "x",
            "_csrf": csrf,
        },
        headers={"X-CSRF-Token": csrf},
    )
    # Now fetch the page; the rendered form should show the DB value.
    r = client.get("/settings")
    assert r.status_code == 200
    assert "FromDB" in r.text
    assert "€" in r.text


def test_html_form_post_works_via_csrf_cookie_field(client: TestClient, session: Session):
    """The base template auto-injects a _csrf hidden input. Server-side we
    accept it from the form body. This test simulates a real form post."""
    _login_as_owner(client, session)
    csrf = client.cookies.get(CSRF_COOKIE)
    # No X-CSRF-Token header; only the _csrf form field.
    r = client.post(
        "/settings",
        data={
            "shop_name": "FormPostShop",
            "shop_address": "",
            "shop_phone": "",
            "currency_symbol": "৳",
            "shop_timezone": "Asia/Dhaka",
            "invoice_footer": "",
            "_csrf": csrf,
        },
    )
    assert r.status_code in (200, 303)
    rows = session.exec(select(Setting)).all()
    by_key = {r.key: r.value for r in rows}
    assert by_key["shop_name"] == "FormPostShop"
    assert by_key["currency_symbol"] == "৳"
