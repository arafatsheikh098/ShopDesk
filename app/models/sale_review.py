"""Sale review: queue for offline sales that could not be safely applied."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SaleReview(SQLModel, table=True):
    __tablename__ = "sale_reviews"

    id: int | None = Field(default=None, primary_key=True)
    idempotency_key: str = Field(index=True, unique=True, min_length=1, max_length=64)
    payload_json: str  # original payload, serialized
    reason: str = Field(max_length=500)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    resolved_at: datetime | None = None
    resolved_by_user_id: int | None = Field(default=None, foreign_key="users.id")
