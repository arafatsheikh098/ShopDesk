"""Generic settings table (key/value)."""
from __future__ import annotations

from sqlmodel import Field, SQLModel


class Setting(SQLModel, table=True):
    __tablename__ = "settings"

    key: str = Field(primary_key=True, min_length=1, max_length=120)
    value: str = Field(default="")
