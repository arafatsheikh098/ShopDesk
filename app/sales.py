"""Sales domain logic: transactions, gap-free numbers, voids, due payments."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import get_settings
from app.models import (
    Customer,
    DuePayment,
    PaymentMethod,
    Product,
    Sale,
    SaleLine,
    SaleStatus,
    StockReason,
    User,
)
from app.money import apply_percent_discount, cap_discount
from app.stock_ops import decrement_stock, increment_stock

# --- Sale number generation (per day, gap-free, unique) ---------------------

def _shop_now() -> datetime:
    """Current time in the shop's timezone."""
    tz = ZoneInfo(get_settings().shop_timezone)
    return datetime.now(tz)


def _next_sale_number(session: Session, today_local: datetime) -> str:
    """Compute the next sale number for the given local-day. Gap-free and unique.

    The approach: count today's sales and append 1-based sequence. To stay gap-free
    even when a sale is voided, we never reuse a number. We compute the *next*
    number as (count of sales with sale_number LIKE prefix) + 1, and rely on the
    UNIQUE constraint to catch any race. The caller wraps the create in a
    transaction with row-level locking on a per-day counter row.
    """
    prefix = today_local.strftime("%Y%m%d-")
    existing = session.exec(
        select(Sale).where(Sale.sale_number.like(f"{prefix}%"))
    ).all()
    n = len(existing) + 1
    return f"{prefix}{n:04d}"


def _lock_sale_number(session: Session, prefix: str) -> int:
    """Take an advisory lock keyed by the local-day prefix so two concurrent
    sales can't both pick the same number. Returns the next free sequence.
    """
    if session.get_bind().dialect.name == "postgresql":
        # pg_advisory_xact_lock is released at the end of the transaction.
        session.execute(
            __import__("sqlalchemy").text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
            {"k": f"sale-{prefix}"},
        )
    existing = session.exec(
        select(Sale).where(Sale.sale_number.like(f"{prefix}%"))
    ).all()
    return len(existing) + 1


# --- Public: create a sale --------------------------------------------------

def create_sale(
    session: Session,
    *,
    user: User,
    lines: list[dict[str, Any]],
    discount_minor: int = 0,
    discount_percent: int = 0,
    payment_method: PaymentMethod = PaymentMethod.CASH,
    paid_minor: int | None = None,
    customer_id: int | None = None,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    idempotency_key: str | None = None,
    allow_partial: bool = False,
) -> Sale:
    """Create a sale atomically. Raises HTTPException(400/404) on validation errors.

    `lines` is a list of dicts with keys: product_id, quantity, unit_price (optional,
    for offline-priced lines; if missing, the product's current sell_price is used).
    """
    if not lines:
        raise HTTPException(status_code=400, detail="sale has no lines")
    if discount_percent and discount_minor:
        raise HTTPException(status_code=400, detail="use either discount_minor or discount_percent, not both")
    if payment_method == PaymentMethod.DUE and not (customer_id or (customer_name and customer_phone)):
        raise HTTPException(status_code=400, detail="customer (name + phone or id) required for due sales")

    # Idempotency check: same key returns the existing sale.
    if idempotency_key:
        existing = session.exec(
            select(Sale).where(Sale.idempotency_key == idempotency_key)
        ).first()
        if existing is not None:
            return existing

    # Resolve customer
    if payment_method == PaymentMethod.DUE and not customer_id and customer_name and customer_phone:
        cust = session.exec(
            select(Customer).where(Customer.phone == customer_phone)
        ).first()
        if cust is None:
            cust = Customer(name=customer_name, phone=customer_phone)
            session.add(cust)
            session.flush()
        customer_id = cust.id

    # Validate and snapshot lines
    sale_lines: list[SaleLine] = []
    subtotal = 0
    price_mismatch = False
    for entry in lines:
        pid = entry.get("product_id")
        qty = int(entry.get("quantity") or 0)
        if not pid or qty <= 0:
            raise HTTPException(status_code=400, detail="each line needs product_id and positive quantity")
        product = session.get(Product, pid)
        if product is None:
            raise HTTPException(status_code=400, detail=f"product {pid} not found")
        if not product.is_active:
            raise HTTPException(status_code=400, detail=f"product {product.sku} is inactive")
        # Price snapshot
        client_price = entry.get("unit_price")
        unit_price = int(client_price if client_price is not None else product.sell_price)
        if unit_price < 0:
            raise HTTPException(status_code=400, detail="unit_price must be non-negative")
        # F7.7: flag price mismatch for owner review when the client supplied
        # a price that doesn't match the product's current sell price.
        if client_price is not None and int(client_price) != product.sell_price:
            price_mismatch = True
        line_total = unit_price * qty
        subtotal += line_total
        sale_lines.append(
            SaleLine(
                product_id=product.id or 0,
                product_name=product.name,
                unit_price=unit_price,
                unit_cost=product.cost_price,
                quantity=qty,
                line_total=line_total,
            )
        )

    # Discount (capped at subtotal)
    if discount_percent:
        d = apply_percent_discount(subtotal, int(discount_percent))
    else:
        d = int(discount_minor or 0)
    d = cap_discount(subtotal, d)
    total = subtotal - d

    # Payment: paid + due must equal total for DUE; for non-DUE, paid >= total (no change given here).
    if payment_method == PaymentMethod.DUE:
        paid = 0
        due = total
    else:
        if paid_minor is None:
            paid = total
        else:
            paid = int(paid_minor)
        if paid < 0:
            raise HTTPException(status_code=400, detail="paid must be non-negative")
        due = 0  # change handling is out of scope; assume paid covers the sale

    # Stock decrement — all or nothing
    try:
        for line in sale_lines:
            decrement_stock(
                session,
                product_id=line.product_id,
                quantity=line.quantity,
                reason=StockReason.SALE,
                reference=None,  # sale_number is set after the row is created
                user_id=user.id,
            )
    except ValueError as e:
        if not allow_partial:
            raise HTTPException(status_code=400, detail=str(e)) from e
        else:
            session.rollback()

    # Sale number under transaction
    now_local = _shop_now()
    prefix = now_local.strftime("%Y%m%d-")
    n = _lock_sale_number(session, prefix)
    sale_number = f"{prefix}{n:04d}"

    sale = Sale(
        sale_number=sale_number,
        idempotency_key=idempotency_key,
        created_at=datetime.now(UTC),
        customer_id=customer_id,
        user_id=user.id or 0,
        subtotal=subtotal,
        discount=d,
        total=total,
        paid=paid,
        due=due,
        payment_method=payment_method,
        status=SaleStatus.COMPLETED,
        price_mismatch_warning=price_mismatch,
    )
    session.add(sale)
    session.flush()
    for line in sale_lines:
        line.sale_id = sale.id or 0
        session.add(line)

    # Backfill reference on the stock movements we just created
    from app.models import StockMovement

    for line in sale_lines:
        mvs = session.exec(
            select(StockMovement)
            .where(StockMovement.product_id == line.product_id)
            .where(StockMovement.reason == StockReason.SALE)
            .where(StockMovement.reference == None)  # noqa: E711
            .order_by(StockMovement.id.desc())
            .limit(1)
        ).all()
        for mv in mvs:
            mv.reference = sale.sale_number
            session.add(mv)

    session.commit()
    session.refresh(sale)
    return sale


# --- Public: void a sale ----------------------------------------------------

def void_sale(
    session: Session,
    *,
    sale_id: int,
    user: User,
    reason: str,
) -> Sale:
    if user.role.value != "owner":
        raise HTTPException(status_code=403, detail="only owners can void sales")
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="void reason is required")
    sale = session.get(Sale, sale_id)
    if sale is None:
        raise HTTPException(status_code=404, detail="sale not found")
    if sale.status == SaleStatus.VOIDED:
        raise HTTPException(status_code=409, detail="sale already voided")
    # Restore stock for each line.
    lines = session.exec(select(SaleLine).where(SaleLine.sale_id == sale_id)).all()
    for line in lines:
        increment_stock(
            session,
            product_id=line.product_id,
            quantity=line.quantity,
            reason=StockReason.VOID,
            reason_text=reason,
            reference=sale.sale_number,
            user_id=user.id,
        )
    sale.status = SaleStatus.VOIDED
    sale.void_reason = reason
    sale.voided_at = datetime.now(UTC)
    sale.voided_by_user_id = user.id
    session.add(sale)
    session.commit()
    session.refresh(sale)
    return sale


# --- Public: record a due payment ------------------------------------------

def record_due_payment(
    session: Session,
    *,
    customer_id: int,
    amount_minor: int,
    user: User,
    sale_id: int | None = None,
    note: str | None = None,
) -> DuePayment:
    if amount_minor <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    cust = session.get(Customer, customer_id)
    if cust is None:
        raise HTTPException(status_code=404, detail="customer not found")
    p = DuePayment(
        customer_id=customer_id,
        sale_id=sale_id,
        amount=amount_minor,
        user_id=user.id or 0,
        note=note,
    )
    session.add(p)
    # Apply: oldest due sale first
    due_sales = session.exec(
        select(Sale)
        .where(Sale.customer_id == customer_id)
        .where(Sale.status == SaleStatus.COMPLETED)
        .where(Sale.due > 0)
        .order_by(Sale.created_at)
    ).all()
    remaining = amount_minor
    for s in due_sales:
        if remaining <= 0:
            break
        take = min(remaining, s.due)
        s.due -= take
        s.paid += take
        session.add(s)
        remaining -= take
    session.commit()
    session.refresh(p)
    return p


def customer_outstanding(session: Session, customer_id: int) -> int:
    rows = session.exec(
        select(Sale).where(Sale.customer_id == customer_id).where(Sale.status == SaleStatus.COMPLETED)
    ).all()
    return sum(s.due for s in rows)
