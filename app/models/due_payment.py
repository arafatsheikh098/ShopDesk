"""Due payment: a payment against an outstanding customer balance."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DuePayment(SQLModel, table=True):
    __tablename__ = "due_payments"

    id: int | None = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customers.id", index=True)
    sale_id: int | None = Field(default=None, foreign_key="sales.id", index=True)
    amount: int = Field(gt=0)  # minor units
    user_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    note: str | None = Field(default=None, max_length=500)
