"""Sale model with idempotency key for offline-safe POSTs."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SaleStatus(str, Enum):
    COMPLETED = "completed"
    VOIDED = "voided"


class PaymentMethod(str, Enum):
    CASH = "cash"
    MOBILE_WALLET = "mobile_wallet"
    DUE = "due"


class Sale(SQLModel, table=True):
    __tablename__ = "sales"

    id: int | None = Field(default=None, primary_key=True)
    sale_number: str = Field(index=True, unique=True, min_length=1, max_length=32)
    idempotency_key: str | None = Field(default=None, index=True, unique=True, max_length=64)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    customer_id: int | None = Field(default=None, foreign_key="customers.id")
    user_id: int = Field(foreign_key="users.id")
    subtotal: int = Field(ge=0)  # minor units
    discount: int = Field(default=0, ge=0)  # minor units
    total: int = Field(ge=0)  # minor units
    paid: int = Field(ge=0)  # minor units
    due: int = Field(default=0, ge=0)  # minor units
    payment_method: PaymentMethod = Field(default=PaymentMethod.CASH, index=True)
    status: SaleStatus = Field(default=SaleStatus.COMPLETED, index=True)
    void_reason: str | None = Field(default=None, max_length=500)
    voided_at: datetime | None = None
    voided_by_user_id: int | None = Field(default=None, foreign_key="users.id")
    needs_review: bool = Field(default=False, index=True)
    review_reason: str | None = Field(default=None, max_length=500)
    price_mismatch_warning: bool = Field(default=False)
