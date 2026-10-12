"""Reports: daily, monthly, top products, profit, outstanding dues."""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.config import get_settings
from app.models import Customer, Sale, SaleLine, SaleStatus


def _shop_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().shop_timezone)


def _local_day_bounds(d: date) -> tuple[datetime, datetime]:
    tz = _shop_tz()
    start = datetime.combine(d, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))


def _local_month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    tz = _shop_tz()
    start = datetime(year, month, 1, tzinfo=tz)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=tz)
    else:
        end = datetime(year, month + 1, 1, tzinfo=tz)
    return start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))


def _completed_sales(session: Session, start_utc: datetime, end_utc: datetime) -> list[Sale]:
    stmt = (
        select(Sale)
        .where(Sale.status == SaleStatus.COMPLETED)
        .where(Sale.created_at >= start_utc)
        .where(Sale.created_at < end_utc)
    )
    return list(session.exec(stmt).all())


def daily_report(session: Session, d: date) -> dict[str, Any]:
    start, end = _local_day_bounds(d)
    sales = _completed_sales(session, start, end)
    return _summarize(sales, session)


def monthly_report(session: Session, year: int, month: int) -> dict[str, Any]:
    start, end = _local_month_bounds(year, month)
    sales = _completed_sales(session, start, end)
    return _summarize(sales, session)


def _summarize(sales: list[Sale], session: Session) -> dict[str, Any]:
    by_method: dict[str, int] = defaultdict(int)
    for s in sales:
        by_method[s.payment_method.value] += s.paid  # amount actually paid
    top_products: dict[tuple[int, str], int] = defaultdict(int)
    sale_ids = [s.id for s in sales if s.id is not None]
    lines: list[SaleLine] = []
    if sale_ids:
        lines = list(
            session.exec(select(SaleLine).where(SaleLine.sale_id.in_(sale_ids))).all()
        )
    for ln in lines:
        key = (ln.product_id, ln.product_name)
        top_products[key] += ln.quantity
    top = sorted(top_products.items(), key=lambda kv: -kv[1])[:10]
    total = sum(s.total for s in sales)
    subtotal = sum(s.subtotal for s in sales)
    discount = sum(s.discount for s in sales)
    cost_total = sum(ln.unit_cost * ln.quantity for ln in lines)
    # Profit = sum((unit_price - unit_cost) * qty) - discount
    profit_per_line = sum(
        (ln.unit_price - ln.unit_cost) * ln.quantity for ln in lines
    )
    profit = profit_per_line - discount
    outstanding = sum(s.due for s in sales if s.due > 0)
    return {
        "sales_count": len(sales),
        "total": total,
        "subtotal": subtotal,
        "discount": discount,
        "cost_total": cost_total,
        "profit": profit,
        "by_method": dict(by_method),
        "top_products": [
            {"product_id": pid, "name": name, "quantity": q}
            for (pid, name), q in top
        ],
        "outstanding": outstanding,
    }


def outstanding_per_customer(session: Session) -> list[dict[str, Any]]:
    rows = list(
        session.exec(
            select(Sale, Customer)
            .join(Customer, Sale.customer_id == Customer.id)
            .where(Sale.status == SaleStatus.COMPLETED)
            .where(Sale.due > 0)
            .order_by(Customer.name)
        ).all()
    )
    out: dict[int, dict[str, Any]] = {}
    for sale, cust in rows:
        e = out.setdefault(cust.id or 0, {"id": cust.id, "name": cust.name, "phone": cust.phone, "due": 0})
        e["due"] += sale.due
    return sorted(out.values(), key=lambda r: -r["due"])


# --- CSV export with formula-injection neutralization --------------------

_NEUTRALIZE_PREFIXES = ("=", "+", "-", "@")


def _neutralize(cell: Any) -> str:
    s = str(cell)
    if s and s[0] in _NEUTRALIZE_PREFIXES:
        return "'" + s
    return s


def sales_to_csv(sales: list[Sale], lines_by_sale: dict[int, list[SaleLine]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "sale_number",
            "created_at",
            "customer_name",
            "payment_method",
            "status",
            "subtotal_minor",
            "discount_minor",
            "total_minor",
            "paid_minor",
            "due_minor",
            "items",
        ]
    )
    for s in sales:
        items = "; ".join(
            f"{ln.product_name} x{ln.quantity} @ {ln.unit_price}" for ln in lines_by_sale.get(s.id or 0, [])
        )
        w.writerow(
            [
                s.sale_number,
                s.created_at.isoformat(),
                _neutralize(getattr(s, "_customer_name", "") or ""),
                s.payment_method.value,
                s.status.value,
                s.subtotal,
                s.discount,
                s.total,
                s.paid,
                s.due,
                _neutralize(items),
            ]
        )
    return buf.getvalue().encode("utf-8")
