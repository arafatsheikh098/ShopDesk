"""Idempotent seed test: run twice, counts are stable."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine
from sqlmodel import Session, select

from app.db import set_engine
from app.models import Category, Customer, Product, User


def _run_seed(env_db: str) -> None:
    env = {**os.environ, "DATABASE_URL": env_db, "APP_ENV": "development", "SECRET_KEY": "x" * 32}
    r = subprocess.run(
        ["python", "scripts/seed.py"],
        env=env, capture_output=True, text=True, check=True, cwd=Path(__file__).resolve().parent.parent,
    )
    assert "users=" in r.stdout


def test_seed_is_idempotent(tmp_path: Path):
    db = tmp_path / "seed.db"
    env_db = f"sqlite:///{db}"
    _run_seed(env_db)
    eng = create_engine(env_db)
    set_engine(eng)
    with Session(eng) as s:
        users1 = len(s.exec(select(User)).all())
        products1 = len(s.exec(select(Product)).all())
        customers1 = len(s.exec(select(Customer)).all())
        categories1 = len(s.exec(select(Category)).all())
    # Run again.
    _run_seed(env_db)
    with Session(eng) as s:
        users2 = len(s.exec(select(User)).all())
        products2 = len(s.exec(select(Product)).all())
        customers2 = len(s.exec(select(Customer)).all())
        categories2 = len(s.exec(select(Category)).all())
    assert users1 == users2 == 1
    assert categories1 == categories2 == 6
    assert products1 == products2 == 50
    assert customers1 == customers2 == 3


def test_seed_creates_known_product(tmp_path: Path):
    db = tmp_path / "seed2.db"
    env_db = f"sqlite:///{db}"
    _run_seed(env_db)
    eng = create_engine(env_db)
    set_engine(eng)
    with Session(eng) as s:
        rice = s.exec(select(Product).where(Product.sku == "RG-RICE-1")).first()
        assert rice is not None
        assert rice.sell_price == 16000  # 160 taka in paisa
        assert rice.barcode == "8901111000012"
        cust = s.exec(select(Customer).where(Customer.phone == "01711000001")).first()
        assert cust is not None
        assert cust.name == "Rakib Hasan"
