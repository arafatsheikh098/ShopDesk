"""Backup/restore round-trip on SQLite."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from sqlmodel import Session, select

from app.auth import hash_password
from app.db import create_db_and_tables, get_engine, set_engine
from app.models import (
    Product,
    Sale,
    SaleLine,
    StockMovement,
    StockReason,
    User,
    UserRole,
)


def test_backup_restore_sqlite_round_trip(tmp_path: Path):
    # 1) Build a database in a temp dir, populate it, back it up.
    db = tmp_path / "shopdesk.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db}",
        "APP_ENV": "development",
        "SECRET_KEY": "round-trip-secret-1234567890",
    }
    # Create schema and seed in this subprocess to keep state clean.
    code = f"""
import os
from app.db import set_engine, get_engine, create_db_and_tables
from sqlmodel import Session
from app.models import User, UserRole, Product, Sale, SaleLine, StockMovement, StockReason
from app.auth import hash_password
from sqlalchemy import create_engine
eng = create_engine("sqlite:///{db}")
set_engine(eng)
create_db_and_tables()
with Session(eng) as s:
    s.add(User(username='owner', password_hash=hash_password('pw'), role=UserRole.OWNER))
    p = Product(name='A', sku='A1', sell_price=100, cost_price=50, stock=10)
    s.add(p)
    s.commit()
    # One sale that drops stock to 9 + a ledger entry.
    sale = Sale(sale_number='X-1', subtotal=100, discount=0, total=100, paid=100, due=0, status='completed', payment_method='cash', user_id=1)
    s.add(sale)
    s.commit()
    s.add(SaleLine(sale_id=sale.id, product_id=p.id, product_name='A', quantity=1, unit_price=100, unit_cost=50, line_total=100))
    s.add(StockMovement(product_id=p.id, delta=-1, reason=StockReason.SALE, reference=str(sale.id), user_id=1))
    p.stock = 9
    s.commit()
    print('SEED OK', p.id, sale.id)
"""
    r = subprocess.run(
        ["python", "-c", code],
        env=env, capture_output=True, text=True, check=True,
    )
    assert "SEED OK" in r.stdout
    # Capture counts.
    set_engine(None)
    eng = get_engine()  # will be rebuilt from env
    # Force the engine to point to the temp db:
    from sqlalchemy import create_engine as _ce
    eng2 = _ce(f"sqlite:///{db}")
    set_engine(eng2)
    with Session(eng2) as s:
        users = s.exec(select(User)).all()
        products = s.exec(select(Product)).all()
        sales = s.exec(select(Sale)).all()
        mvs = s.exec(select(StockMovement)).all()
        assert len(users) == 1
        assert len(products) == 1
        assert len(sales) == 1
        assert len(mvs) == 1
        original_product = products[0]
        original_sale = sales[0]
        assert original_product.stock == 9

    # 2) Run the backup script.
    backup_dir = tmp_path / "backups"
    r = subprocess.run(
        ["bash", "scripts/backup.sh", str(backup_dir)],
        env=env, capture_output=True, text=True, check=True,
    )
    archive = Path(r.stdout.strip().splitlines()[-1])
    assert archive.exists() and archive.suffix == ".gz"

    # 3) Wipe the database and restore.
    db.unlink()
    r = subprocess.run(
        ["bash", "scripts/restore.sh", str(archive)],
        env=env, capture_output=True, text=True, check=True,
    )
    assert "restored" in r.stdout

    # 4) Verify counts and stock totals match.
    eng3 = _ce(f"sqlite:///{db}")
    set_engine(eng3)
    with Session(eng3) as s:
        users2 = s.exec(select(User)).all()
        products2 = s.exec(select(Product)).all()
        sales2 = s.exec(select(Sale)).all()
        mvs2 = s.exec(select(StockMovement)).all()
        assert len(users2) == 1
        assert len(products2) == 1
        assert len(sales2) == 1
        assert len(mvs2) == 1
        assert products2[0].stock == 9
        assert products2[0].id == original_product.id
        assert sales2[0].id == original_sale.id
        assert sales2[0].sale_number == "X-1"
