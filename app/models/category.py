"""Category model."""
from __future__ import annotations

from sqlmodel import Field, SQLModel


class Category(SQLModel, table=True):
    __tablename__ = "categories"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, min_length=1, max_length=120)
