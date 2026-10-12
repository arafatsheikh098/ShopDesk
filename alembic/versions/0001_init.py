"""initial schema

Revision ID: 0001_init
Revises:
Create Date: 2026-10-12
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, index=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True, index=True),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, index=True),
        sa.Column("sku", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("barcode", sa.String(64), nullable=True, unique=True, index=True),
        sa.Column("unit", sa.String(32), nullable=False, server_default="pcs"),
        sa.Column("sell_price", sa.Integer, nullable=False),
        sa.Column("cost_price", sa.Integer, nullable=False),
        sa.Column("low_stock_threshold", sa.Integer, nullable=False, server_default="0"),
        sa.Column("stock", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true"), index=True),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("categories.id"), nullable=True, index=True),
    )
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("delta", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(16), nullable=False, index=True),
        sa.Column("reason_text", sa.String(500), nullable=True),
        sa.Column("reference", sa.String(120), nullable=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), index=True),
    )
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, index=True),
        sa.Column("phone", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "sales",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sale_number", sa.String(32), nullable=False, unique=True, index=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True, unique=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), index=True),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("subtotal", sa.Integer, nullable=False),
        sa.Column("discount", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total", sa.Integer, nullable=False),
        sa.Column("paid", sa.Integer, nullable=False),
        sa.Column("due", sa.Integer, nullable=False, server_default="0"),
        sa.Column("payment_method", sa.String(16), nullable=False, index=True),
        sa.Column("status", sa.String(16), nullable=False, index=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("needs_review", sa.Boolean, nullable=False, server_default=sa.text("false"), index=True),
        sa.Column("review_reason", sa.String(500), nullable=True),
        sa.Column("price_mismatch_warning", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "sale_lines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sale_id", sa.Integer, sa.ForeignKey("sales.id"), nullable=False, index=True),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("unit_price", sa.Integer, nullable=False),
        sa.Column("unit_cost", sa.Integer, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("line_total", sa.Integer, nullable=False),
    )
    op.create_table(
        "due_payments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("sale_id", sa.Integer, sa.ForeignKey("sales.id"), nullable=True, index=True),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), index=True),
        sa.Column("note", sa.String(500), nullable=True),
    )
    op.create_table(
        "sale_reviews",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), index=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(120), primary_key=True),
        sa.Column("value", sa.String, nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_table("sale_reviews")
    op.drop_table("due_payments")
    op.drop_table("sale_lines")
    op.drop_table("sales")
    op.drop_table("customers")
    op.drop_table("stock_movements")
    op.drop_table("products")
    op.drop_table("categories")
    op.drop_table("users")
