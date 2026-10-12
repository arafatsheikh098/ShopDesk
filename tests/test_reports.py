"""Reports tests: timezone, profit worked example, CSV injection, owner-only."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from sqlmodel import Session, select

from app.auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    hash_password,
    make_csrf_token,
    make_session_cookie,
)
from app.models import (
    Customer,
    PaymentMethod,
    Product,
    Sale,
    SaleLine,
    SaleStatus,
    User,
    UserRole,
)
from app.reports import _summarize, daily_report, monthly_report, sales_to_csv


def _login_as(client: TestClient, session: Session, username: str) -> None:
    user = next(u for u in session.exec(select(User)) if u.username == username)
    token = make_session_cookie(user.id or 0)
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, make_csrf_token(token))


# ---- A2: timezone day boundary (Asia/Dhaka) ----------------------------

def test_sale_at_2350_local_is_in_same_day_report(session):
    """A sale at 23:50 Asia/Dhaka must land in that day's report even if the
    UTC timestamp is on the next day.
    """
    # Local time 2026-10-12 23:50 Asia/Dhaka = UTC 2026-10-12 17:50
    local = datetime(2026, 10, 12, 23, 50, tzinfo=ZoneInfo("Asia/Dhaka"))
    utc = local.astimezone(ZoneInfo("UTC"))
    sale = Sale(
        sale_number="20261012-0001",
        created_at=utc,
        user_id=1,
        subtotal=100,
        discount=0,
        total=100,
        paid=100,
        due=0,
        payment_method=PaymentMethod.CASH,
        status=SaleStatus.COMPLETED,
    )
    session.add(sale)
    session.commit()
    session.add(
        SaleLine(
            sale_id=sale.id,
            product_id=1,
            product_name="X",
            unit_price=100,
            unit_cost=50,
            quantity=1,
            line_total=100,
        )
    )
    session.commit()
    report = daily_report(session, date(2026, 10, 12))
    assert report["sales_count"] == 1
    # Sale at 00:05 local on 2026-10-13 should NOT be in 2026-10-12's report.
    sale2 = Sale(
        sale_number="20261013-0001",
        created_at=datetime(2026, 10, 12, 18, 6, tzinfo=ZoneInfo("UTC")),  # = 00:06 next day local
        user_id=1,
        subtotal=50,
        discount=0,
        total=50,
        paid=50,
        due=0,
        payment_method=PaymentMethod.CASH,
        status=SaleStatus.COMPLETED,
    )
    session.add(sale2)
    session.commit()
    session.add(
        SaleLine(
            sale_id=sale2.id,
            product_id=1,
            product_name="Y",
            unit_price=50,
            unit_cost=20,
            quantity=1,
            line_total=50,
        )
    )
    session.commit()
    report = daily_report(session, date(2026, 10, 12))
    assert report["sales_count"] == 1
    report_next = daily_report(session, date(2026, 10, 13))
    assert report_next["sales_count"] == 1


# ---- A3: profit worked example ----------------------------------------

def test_profit_is_line_profit_minus_discount(session):
    # 2 lines: (100-40)*3 = 180, (200-100)*2 = 200; total line profit = 380; discount=30; profit=350
    s1 = Sale(
        sale_number="20261012-0001",
        created_at=datetime(2026, 10, 12, 10, 0, tzinfo=ZoneInfo("UTC")),
        user_id=1,
        subtotal=700,
        discount=30,
        total=670,
        paid=670,
        due=0,
        payment_method=PaymentMethod.CASH,
        status=SaleStatus.COMPLETED,
    )
    session.add(s1)
    session.commit()
    session.add(
        SaleLine(
            sale_id=s1.id,
            product_id=1,
            product_name="A",
            unit_price=100,
            unit_cost=40,
            quantity=3,
            line_total=300,
        )
    )
    session.add(
        SaleLine(
            sale_id=s1.id,
            product_id=2,
            product_name="B",
            unit_price=200,
            unit_cost=100,
            quantity=2,
            line_total=400,
        )
    )
    session.commit()
    sales = list(session.exec(select(Sale).where(Sale.id == s1.id)).all())
    lines = list(session.exec(select(SaleLine).where(SaleLine.sale_id == s1.id)).all())
    rep = _summarize(sales, session)
    assert rep["profit"] == 350  # 380 - 30
    assert rep["by_method"]["cash"] == 670
    assert rep["total"] == 670


# ---- A4: only owners can open reports ----------------------------------

def test_reports_owner_only(client, session):
    session.add(
        User(username="c", password_hash=hash_password("pw"), role=UserRole.CASHIER)
    )
    session.commit()
    _login_as(client, session, "c")
    r = client.get("/reports/daily")
    assert r.status_code == 403
    r = client.get("/reports/monthly")
    assert r.status_code == 403
    r = client.get("/reports/dues")
    assert r.status_code == 403
    r = client.get("/reports/export.csv")
    assert r.status_code == 403


# ---- A5: CSV export neutralizes =, +, -, @ in text fields -------------

def test_csv_neutralizes_dangerous_prefixes():
    sales = [
        Sale(
            id=1,
            sale_number="20261012-0001",
            created_at=datetime(2026, 10, 12, 10, 0, tzinfo=ZoneInfo("UTC")),
            user_id=1,
            subtotal=100,
            discount=0,
            total=100,
            paid=100,
            due=0,
            payment_method=PaymentMethod.CASH,
            status=SaleStatus.COMPLETED,
        )
    ]
    setattr(sales[0], "_customer_name", "=cmd|' /C calc'!A1")
    lines = {
        1: [
            SaleLine(
                id=1,
                sale_id=1,
                product_id=1,
                product_name="+evil",
                unit_price=100,
                unit_cost=50,
                quantity=1,
                line_total=100,
            )
        ]
    }
    body = sales_to_csv(sales, lines).decode("utf-8")
    reader = list(csv.reader(io.StringIO(body)))
    assert reader[1][2].startswith("'=")  # customer name neutralized
    assert "; ".join(["+evil"]) in body or "'+evil" in body
    # And the literal bare "=cmd" or "+evil" do NOT appear as a first cell char
    for row in reader[1:]:
        for cell in row:
            if cell:
                assert not cell.startswith(("=", "+", "-", "@")), cell
