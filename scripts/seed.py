"""Idempotent demo seed.

Creates:
- One owner (username=owner, password=owner123) if not present.
- 50 grocery products across a few categories.
- 3 customers.

Re-running is a no-op: existing rows are detected by unique keys (username,
SKU, customer phone) and skipped. Counts are printed at the end.

Usage:
    python scripts/seed.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/seed.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.db import create_db_and_tables, get_engine  # noqa: E402
from app.models import (  # noqa: E402
    Category,
    Customer,
    Product,
    User,
    UserRole,
)

CATEGORIES = [
    ("Rice & Grains", "RG"),
    ("Oils & Spices", "OS"),
    ("Snacks & Biscuits", "SB"),
    ("Beverages", "BV"),
    ("Dairy & Eggs", "DE"),
    ("Pulses & Lentils", "PL"),
]

PRODUCTS = [
    # (name, sku, sell_taka, cost_taka, stock, cat_code, barcode)
    ("Basmati Rice 5kg", "RG-RICE-5", 750, 600, 30, "RG", "8901111000011"),
    ("Basmati Rice 1kg", "RG-RICE-1", 160, 125, 80, "RG", "8901111000012"),
    ("Miniket Rice 5kg", "RG-MINI-5", 520, 420, 40, "RG", "8901111000013"),
    ("Miniket Rice 1kg", "RG-MINI-1", 110, 88, 100, "RG", "8901111000014"),
    ("Chinigura Rice 1kg", "RG-CHIN-1", 200, 160, 60, "RG", "8901111000015"),
    ("Atta 2kg", "RG-ATTA-2", 130, 100, 50, "RG", "8901111000016"),
    ("Maida 1kg", "RG-MAIDA-1", 70, 50, 40, "RG", "8901111000017"),
    ("Suji 500g", "RG-SUJI-05", 55, 40, 30, "RG", "8901111000018"),
    ("Mustard Oil 1L", "OS-MOIL-1", 220, 175, 25, "OS", "8901111000021"),
    ("Soybean Oil 1L", "OS-SOIL-1", 195, 158, 25, "OS", "8901111000022"),
    ("Olive Oil 500ml", "OS-OLV-05", 650, 510, 12, "OS", "8901111000023"),
    ("Turmeric Powder 200g", "OS-TUR-02", 95, 70, 40, "OS", "8901111000024"),
    ("Red Chilli Powder 200g", "OS-CHIL-02", 120, 90, 40, "OS", "8901111000025"),
    ("Coriander Powder 200g", "OS-COR-02", 80, 60, 35, "OS", "8901111000026"),
    ("Cumin Powder 100g", "OS-CUM-01", 90, 65, 30, "OS", "8901111000027"),
    ("Salt 1kg", "OS-SALT-1", 35, 22, 100, "OS", "8901111000028"),
    ("Sugar 1kg", "OS-SUGA-1", 130, 105, 80, "OS", "8901111000029"),
    ("Tea 400g", "BV-TEA-04", 320, 250, 35, "BV", "8901111000031"),
    ("Coffee 200g", "BV-COF-02", 450, 350, 20, "BV", "8901111000032"),
    ("Milk 1L", "DE-MILK-1", 90, 70, 50, "DE", "8901111000033"),
    ("Milk Powder 1kg", "DE-MILK-1K", 720, 580, 15, "DE", "8901111000034"),
    ("Butter 200g", "DE-BUT-02", 220, 175, 18, "DE", "8901111000035"),
    ("Eggs (12)", "DE-EGG-12", 140, 110, 25, "DE", "8901111000036"),
    ("Yogurt 500g", "DE-YOG-05", 80, 60, 20, "DE", "8901111000037"),
    ("Cheese 200g", "DE-CHE-02", 380, 310, 12, "DE", "8901111000038"),
    ("Biscuits (cream)", "SB-BISC-CR", 40, 28, 60, "SB", "8901111000041"),
    ("Biscuits (chocolate)", "SB-BISC-CH", 50, 35, 60, "SB", "8901111000042"),
    ("Chips (salt)", "SB-CHIP-SA", 30, 20, 70, "SB", "8901111000043"),
    ("Chips (masala)", "SB-CHIP-MA", 35, 24, 70, "SB", "8901111000044"),
    ("Noodles (masala)", "SB-NOOD-MA", 25, 16, 90, "SB", "8901111000045"),
    ("Noodles (curry)", "SB-NOOD-CU", 25, 16, 90, "SB", "8901111000046"),
    ("Cake (vanilla)", "SB-CAKE-VA", 120, 90, 20, "SB", "8901111000047"),
    ("Bread (white)", "BV-BREAD-W", 55, 38, 30, "BV", "8901111000051"),
    ("Bread (brown)", "BV-BREAD-B", 70, 50, 25, "BV", "8901111000052"),
    ("Juice (orange) 1L", "BV-JUI-OR-1", 180, 140, 18, "BV", "8901111000053"),
    ("Juice (mango) 1L", "BV-JUI-MG-1", 200, 158, 18, "BV", "8901111000054"),
    ("Soft Drink 1.5L", "BV-SODA-15", 90, 70, 30, "BV", "8901111000055"),
    ("Soft Drink 500ml", "BV-SODA-05", 35, 25, 60, "BV", "8901111000056"),
    ("Water 1L", "BV-WAT-1", 25, 15, 100, "BV", "8901111000057"),
    ("Lentils (red) 1kg", "PL-LEN-R-1", 170, 135, 50, "PL", "8901111000061"),
    ("Lentils (green) 1kg", "PL-LEN-G-1", 165, 130, 50, "PL", "8901111000062"),
    ("Chickpeas 1kg", "PL-CHIK-1", 150, 118, 40, "PL", "8901111000063"),
    ("Black beans 1kg", "PL-BLKB-1", 180, 142, 35, "PL", "8901111000064"),
    ("Mung beans 1kg", "PL-MUNG-1", 175, 138, 35, "PL", "8901111000065"),
    ("Soybeans 1kg", "PL-SOYB-1", 160, 125, 30, "PL", "8901111000066"),
    ("Flour 1kg", "RG-FL-1", 65, 48, 40, "RG", "8901111000019"),
    ("Honey 500g", "OS-HON-05", 350, 280, 15, "OS", "890111100002A"),
    ("Vinegar 500ml", "OS-VIN-05", 90, 65, 25, "OS", "890111100002B"),
    ("Ginger paste 200g", "OS-GIN-02", 60, 42, 30, "OS", "890111100002C"),
    ("Garlic paste 200g", "OS-GAR-02", 65, 45, 30, "OS", "890111100002D"),
]

CUSTOMERS = [
    ("Rakib Hasan", "01711000001"),
    ("Sumaiya Akter", "01711000002"),
    ("Mohammad Karim", "01711000003"),
]


def main() -> int:
    create_db_and_tables()
    created_p = 0
    created_c = 0
    created_u = False
    with Session(get_engine()) as s:
        # 1) Owner
        owner = s.exec(select(User).where(User.username == "owner")).first()
        if not owner:
            s.add(
                User(
                    username="owner",
                    password_hash=hash_password("owner123"),
                    role=UserRole.OWNER,
                )
            )
            s.commit()
            created_u = True
        # 2) Categories (idempotent on name)
        cats: dict[str, Category] = {}
        for name, code in CATEGORIES:
            row = s.exec(select(Category).where(Category.name == name)).first()
            if not row:
                row = Category(name=name, code=code)
                s.add(row)
                s.commit()
                s.refresh(row)
            cats[code] = row
        # 3) Products
        for name, sku, sell_taka, cost_taka, stock, cat_code, barcode in PRODUCTS:
            existing = s.exec(select(Product).where(Product.sku == sku)).first()
            if existing:
                continue
            s.add(
                Product(
                    name=name,
                    sku=sku,
                    barcode=barcode,
                    sell_price=sell_taka * 100,
                    cost_price=cost_taka * 100,
                    stock=stock,
                    category_id=cats[cat_code].id,
                )
            )
            s.commit()
            created_p += 1
        # 4) Customers
        for name, phone in CUSTOMERS:
            existing = s.exec(select(Customer).where(Customer.phone == phone)).first()
            if existing:
                continue
            s.add(Customer(name=name, phone=phone))
            s.commit()
            created_c += 1
        # 5) Final counts
        users = s.exec(select(User)).all()
        products = s.exec(select(Product)).all()
        customers = s.exec(select(Customer)).all()
        categories = s.exec(select(Category)).all()
        print(
            f"users={len(users)} categories={len(categories)} products={len(products)} "
            f"customers={len(customers)} (created owner={created_u}, products={created_p}, customers={created_c})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
