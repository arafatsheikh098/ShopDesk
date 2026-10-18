"""Sales tests: money math, void, due, price snapshot, atomic stock."""
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
from app.models import (
    Customer,
    PaymentMethod,
    Product,
    Sale,
    SaleLine,
    User,
    UserRole,
)
from app.sales import create_sale


def _seed(session: Session, role: UserRole, username: str) -> User:
    u = User(username=username, password_hash=hash_password("pw"), role=role)
    session.add(u)
    session.commit()
    return u


def _login_as(client: TestClient, session: Session, username: str) -> None:
    user = next(u for u in session.exec(select(User)) if u.username == username)
    token = make_session_cookie(user.id or 0)
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, make_csrf_token(token))


def _make_product(session: Session, *, sku: str, sell: int, cost: int, stock: int = 10) -> Product:
    p = Product(name=sku, sku=sku, sell_price=sell, cost_price=cost, stock=stock)
    session.add(p)
    session.commit()
    return p


# ---- A1: exact money math for total/discount/percent --------------------

@pytest.mark.parametrize(
    "lines,kind,value,expected_subtotal,expected_discount,expected_total",
    [
        # 0% discount
        ([{"sell": 100, "qty": 1}], "none", 0, 100, 0, 100),
        # 100% discount
        ([{"sell": 250, "qty": 2}], "percent", 100, 500, 500, 0),
        # Over-cap percent (200% on a 100 sale) — rejected (percent must be 0..100)
        # Discount over the subtotal via `amount` is the supported way to zero out.
        # (this row is replaced below by a positive test of amount over-cap)
        # Odd amounts: percent rounding
        ([{"sell": 333, "qty": 1}], "percent", 10, 333, 33, 300),
        # Discount amount equal to subtotal
        ([{"sell": 199, "qty": 3}], "amount", 597, 597, 597, 0),
        # Discount amount over subtotal — capped
        ([{"sell": 100, "qty": 1}], "amount", 9999, 100, 100, 0),
        # 0 discount
        ([{"sell": 12, "qty": 1}], "amount", 0, 12, 0, 12),
    ],
)
def test_money_math_parametrized(
    session, lines, kind, value, expected_subtotal, expected_discount, expected_total
):
    owner = _seed(session, UserRole.OWNER, "o")
    products = []
    for i, ln in enumerate(lines):
        p = _make_product(session, sku=f"P{i}", sell=ln["sell"], cost=1, stock=100)
        products.append(p)
    payload_lines = [
        {"product_id": products[i].id, "quantity": ln["qty"]} for i, ln in enumerate(lines)
    ]
    discount_minor = value if kind == "amount" else 0
    discount_percent = value if kind == "percent" else 0
    sale = create_sale(
        session,
        user=owner,
        lines=payload_lines,
        discount_minor=discount_minor,
        discount_percent=discount_percent,
        payment_method=PaymentMethod.CASH,
    )
    assert sale.subtotal == expected_subtotal
    assert sale.discount == expected_discount
    assert sale.total == expected_total
    assert sale.due == 0
    assert sale.paid == expected_total


# ---- A2: sale that would make stock negative fails as a whole ----------

def test_sale_with_insufficient_stock_fails_atomically(client, session):
    owner = _seed(session, UserRole.OWNER, "o")
    _login_as(client, session, "o")
    p1 = _make_product(session, sku="S1", sell=100, cost=50, stock=2)
    p2 = _make_product(session, sku="S2", sell=200, cost=80, stock=10)
    csrf = client.cookies.get(CSRF_COOKIE)
    r = client.post(
        "/api/sales",
        json={
            "idempotency_key": "k1",
            "lines": [
                {"product_id": p1.id, "quantity": 5},  # would need 5, have 2
                {"product_id": p2.id, "quantity": 1},
            ],
            "payment_method": "cash",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 400
    # Both products' stock unchanged
    s1 = session.get(Product, p1.id)
    s2 = session.get(Product, p2.id)
    assert s1.stock == 2
    assert s2.stock == 10
    # No sale row created
    assert session.exec(select(Sale)).first() is None


# ---- A3: void restores stock exactly once; double void rejected ---------

def test_void_restores_stock_once_then_rejected(client, session):
    owner = _seed(session, UserRole.OWNER, "o")
    _login_as(client, session, "o")
    p = _make_product(session, sku="V1", sell=100, cost=50, stock=10)
    csrf = client.cookies.get(CSRF_COOKIE)
    r = client.post(
        "/api/sales",
        json={
            "idempotency_key": "vk1",
            "lines": [{"product_id": p.id, "quantity": 3}],
            "payment_method": "cash",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    sale_id = r.json()["id"]
    session.expire_all()
    assert session.get(Product, p.id).stock == 7
    r = client.post(
        f"/api/sales/{sale_id}/void",
        json={"reason": "customer returned"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    session.expire_all()
    assert session.get(Product, p.id).stock == 10
    r = client.post(
        f"/api/sales/{sale_id}/void",
        json={"reason": "again"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 409


def test_void_requires_reason(client, session):
    owner = _seed(session, UserRole.OWNER, "o")
    _login_as(client, session, "o")
    p = _make_product(session, sku="V2", sell=100, cost=50, stock=10)
    csrf = client.cookies.get(CSRF_COOKIE)
    r = client.post(
        "/api/sales",
        json={
            "idempotency_key": "vk2",
            "lines": [{"product_id": p.id, "quantity": 1}],
            "payment_method": "cash",
        },
        headers={"X-CSRF-Token": csrf},
    )
    sale_id = r.json()["id"]
    r = client.post(
        f"/api/sales/{sale_id}/void",
        json={"reason": ""},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 400


# ---- A4: due sale requires customer -------------------------------------

def test_due_sale_without_customer_rejected(client, session):
    owner = _seed(session, UserRole.OWNER, "o")
    _login_as(client, session, "o")
    p = _make_product(session, sku="D1", sell=100, cost=50, stock=10)
    csrf = client.cookies.get(CSRF_COOKIE)
    r = client.post(
        "/api/sales",
        json={
            "idempotency_key": "due1",
            "lines": [{"product_id": p.id, "quantity": 1}],
            "payment_method": "due",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 400
    assert "customer" in r.json()["detail"].lower()


def test_due_sale_records_outstanding(client, session):
    owner = _seed(session, UserRole.OWNER, "o")
    _login_as(client, session, "o")
    p = _make_product(session, sku="D2", sell=100, cost=50, stock=10)
    csrf = client.cookies.get(CSRF_COOKIE)
    r = client.post(
        "/api/sales",
        json={
            "idempotency_key": "due2",
            "lines": [{"product_id": p.id, "quantity": 2}],
            "payment_method": "due",
            "customer_name": "Alice",
            "customer_phone": "+8801700000000",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["due"] == 200
    cust = session.exec(select(Customer).where(Customer.phone == "+8801700000000")).one()
    # Record a partial payment
    r = client.post(
        "/api/due-payments",
        json={"customer_id": cust.id, "amount_minor": 75},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    sale = session.get(Sale, body["id"])
    assert sale.due == 200 - 75
    assert sale.paid == 75


# ---- A5: price snapshot -------------------------------------------------

def test_changing_product_price_does_not_change_past_sale_lines(client, session):
    owner = _seed(session, UserRole.OWNER, "o")
    _login_as(client, session, "o")
    p = _make_product(session, sku="PZ", sell=100, cost=50, stock=10)
    csrf = client.cookies.get(CSRF_COOKIE)
    r = client.post(
        "/api/sales",
        json={
            "idempotency_key": "pz1",
            "lines": [{"product_id": p.id, "quantity": 2}],
            "payment_method": "cash",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    sale_id = r.json()["id"]
    # Now change the product price.
    p.sell_price = 999
    session.add(p)
    session.commit()
    # Past line still has the old price.
    line = session.exec(select(SaleLine).where(SaleLine.sale_id == sale_id)).one()
    assert line.unit_price == 100
    assert line.line_total == 200


# ---- Sale numbers: unique, gap-free, per-day (Postgres test) ------------

@pytest.mark.skipif(
    "postgresql" not in (os.environ.get("DATABASE_URL") or ""),
    reason="Postgres-only test",
)
def test_concurrent_sale_numbers_unique_and_gap_free_on_postgres():
    """Fire N concurrent create_sale calls and assert all sale_numbers are
    distinct and in the form YYYYMMDD-NNNN.
    """
    import os

    from sqlalchemy import create_engine
    from sqlmodel import Session, SQLModel

    from app.models import Product

    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    SQLModel.metadata.drop_all(eng)
    SQLModel.metadata.create_all(eng)
    from app.db import set_engine

    set_engine(eng)
    try:
        with Session(eng) as s:
            owner = User(username="o", password_hash=hash_password("pw"), role=UserRole.OWNER)
            prod = Product(name="R", sku="R1", sell_price=100, cost_price=50, stock=10000)
            s.add(owner)
            s.add(prod)
            s.commit()
            owner_id = owner.id
            prod_id = prod.id

        results: list[str] = []
        lock = threading.Lock()

        def attempt():
            with Session(eng) as s:
                u = s.get(User, owner_id)
                try:
                    sale = create_sale(
                        s,
                        user=u,
                        lines=[{"product_id": prod_id, "quantity": 1}],
                        payment_method=PaymentMethod.CASH,
                    )
                    with lock:
                        results.append(sale.sale_number)
                except Exception as e:  # pragma: no cover
                    with lock:
                        results.append("ERROR:" + str(e))

        threads = [threading.Thread(target=attempt) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        numbers = [n for n in results if not n.startswith("ERROR")]
        assert len(numbers) == 10
        assert len(set(numbers)) == 10  # all unique
        import re

        pat = re.compile(r"^\d{8}-\d{4}$")
        assert all(pat.match(n) for n in numbers)
        # Sequence 1..10
        seqs = sorted(int(n.split("-")[1]) for n in numbers)
        assert seqs == list(range(1, 11))
    finally:
        set_engine(None)
        eng.dispose()
