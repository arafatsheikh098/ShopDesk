"""Stock movement ledger."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class StockReason(str, Enum):
    OPENING = "opening"
    PURCHASE = "purchase"
    SALE = "sale"
    VOID = "void"
    ADJUSTMENT = "adjustment"


class StockMovement(SQLModel, table=True):
    __tablename__ = "stock_movements"

    id: int | None = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="products.id", index=True)
    delta: int  # signed integer (negative = stock out)
    reason: StockReason = Field(default=StockReason.ADJUSTMENT, index=True)
    reason_text: str | None = Field(default=None, max_length=500)
    reference: str | None = Field(default=None, max_length=120, index=True)
    user_id: int | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=_utcnow, index=True)
