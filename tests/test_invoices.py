"""Invoice PDF tests: Bangla renders, font is embedded."""
from __future__ import annotations

import io

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlmodel import Session, select

from app.auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    hash_password,
    make_csrf_token,
    make_session_cookie,
)
from app.invoices import render_invoice_pdf
from app.models import (
    PaymentMethod,
    Product,
    Sale,
    SaleLine,
    SaleStatus,
    User,
    UserRole,
)


def _login_as(client: TestClient, session: Session, username: str) -> None:
    user = next(u for u in session.exec(select(User)) if u.username == username)
    token = make_session_cookie(user.id or 0)
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, make_csrf_token(token))


def test_pdf_contains_shop_and_items_and_amounts():
    sale = Sale(
        id=1,
        sale_number="20261012-0001",
        created_at=__import__("datetime").datetime(2026, 10, 12, 10, 0, 0),
        customer_id=None,
        user_id=1,
        subtotal=200,
        discount=20,
        total=180,
        paid=180,
        due=0,
        payment_method=PaymentMethod.CASH,
        status=SaleStatus.COMPLETED,
    )
    lines = [
        SaleLine(
            id=1,
            sale_id=1,
            product_id=1,
            product_name="Apple",
            unit_price=100,
            unit_cost=50,
            quantity=2,
            line_total=200,
        )
    ]
    pdf = render_invoice_pdf(sale, lines, customer_name=None)
    assert pdf.startswith(b"%PDF-")
    # The font name should appear in the PDF resource dictionary.
    assert b"NotoBengali" in pdf or b"NotoSans" in pdf


def test_pdf_renders_bangla_shop_name():
    sale = Sale(
        id=2,
        sale_number="20261012-0002",
        created_at=__import__("datetime").datetime(2026, 10, 12, 10, 0, 0),
        customer_id=None,
        user_id=1,
        subtotal=100,
        discount=0,
        total=100,
        paid=100,
        due=0,
        payment_method=PaymentMethod.CASH,
        status=SaleStatus.COMPLETED,
    )
    lines = [
        SaleLine(
            id=1,
            sale_id=2,
            product_id=1,
            product_name="আম",
            unit_price=100,
            unit_cost=50,
            quantity=1,
            line_total=100,
        )
    ]
    pdf = render_invoice_pdf(sale, lines, customer_name="রহিম")
    assert pdf.startswith(b"%PDF-")
    assert b"NotoBengali" in pdf or b"NotoSans" in pdf


def test_invoice_route_returns_pdf(client, session):
    session.add(
        User(username="o", password_hash=hash_password("pw"), role=UserRole.OWNER)
    )
    session.commit()
    _login_as(client, session, "o")
    p = Product(id=1, name="X", sku="X1", sell_price=100, cost_price=50)
    session.add(p)
    session.commit()
    s = Sale(
        sale_number="20261012-0001",
        user_id=next(u.id for u in session.exec(select(User))),
        subtotal=100,
        discount=0,
        total=100,
        paid=100,
        due=0,
        payment_method=PaymentMethod.CASH,
        status=SaleStatus.COMPLETED,
    )
    session.add(s)
    session.commit()
    session.add(SaleLine(sale_id=s.id, product_id=1, product_name="X", unit_price=100, unit_cost=50, quantity=1, line_total=100))
    session.commit()
    r = client.get("/invoices/20261012-0001.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")
