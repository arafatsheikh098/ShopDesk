"""Stock operations: a single helper that updates stock and writes the ledger
entry in the same transaction. Both M3 (receive/adjust) and M4 (sales) use this
so the invariant stock == sum(delta) is preserved.
"""
from __future__ import annotations

from sqlmodel import Session

from app.models import Product, StockMovement, StockReason


def _is_postgres(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


def _lock_product(session: Session, product_id: int) -> Product:
    if _is_postgres(session):
        product = session.get(Product, product_id, with_for_update=True)
    else:
        product = session.get(Product, product_id)
    if product is None:
        raise ValueError("product not found")
    return product


def decrement_stock(
    session: Session,
    product_id: int,
    quantity: int,
    reason: StockReason,
    reference: str | None = None,
    user_id: int | None = None,
) -> None:
    """Decrement product stock atomically and write a ledger row.

    Uses SELECT ... FOR UPDATE on Postgres to serialize concurrent attempts.
    Raises ValueError if the resulting stock would be negative.
    """
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    product = _lock_product(session, product_id)
    new_stock = product.stock - quantity
    if new_stock < 0:
        raise ValueError(
            f"insufficient stock: have {product.stock}, need {quantity}"
        )
    product.stock = new_stock
    mv = StockMovement(
        product_id=product_id,
        delta=-quantity,
        reason=reason,
        reference=reference,
        user_id=user_id,
    )
    session.add(product)
    session.add(mv)


def increment_stock(
    session: Session,
    product_id: int,
    quantity: int,
    reason: StockReason,
    reason_text: str | None = None,
    reference: str | None = None,
    user_id: int | None = None,
) -> None:
    """Increment product stock and write a ledger row (e.g. for void, receive)."""
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    product = _lock_product(session, product_id)
    product.stock = product.stock + quantity
    mv = StockMovement(
        product_id=product_id,
        delta=quantity,
        reason=reason,
        reason_text=reason_text,
        reference=reference,
        user_id=user_id,
    )
    session.add(product)
    session.add(mv)
