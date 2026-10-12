"""Sale line: price and cost snapshot per line."""
from __future__ import annotations

from sqlmodel import Field, SQLModel


class SaleLine(SQLModel, table=True):
    __tablename__ = "sale_lines"

    id: int | None = Field(default=None, primary_key=True)
    sale_id: int = Field(foreign_key="sales.id", index=True)
    product_id: int = Field(foreign_key="products.id", index=True)
    product_name: str = Field(min_length=1, max_length=200)
    unit_price: int = Field(ge=0)  # minor units, snapshot
    unit_cost: int = Field(ge=0)  # minor units, snapshot
    quantity: int = Field(gt=0)
    line_total: int = Field(ge=0)  # minor units, unit_price * quantity
