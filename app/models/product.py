"""Product model. All money is integer minor units (paisa)."""
from __future__ import annotations

from sqlmodel import Field, SQLModel


class Product(SQLModel, table=True):
    __tablename__ = "products"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, min_length=1, max_length=200)
    sku: str = Field(index=True, unique=True, min_length=1, max_length=64)
    barcode: str | None = Field(default=None, index=True, unique=True, max_length=64)
    unit: str = Field(default="pcs", max_length=32)
    sell_price: int = Field(ge=0)  # minor units
    cost_price: int = Field(ge=0)  # minor units
    low_stock_threshold: int = Field(default=0, ge=0)
    stock: int = Field(default=0, ge=0)  # cached value, kept in sync with stock_movements
    is_active: bool = Field(default=True, index=True)
    category_id: int | None = Field(default=None, foreign_key="categories.id", index=True)
