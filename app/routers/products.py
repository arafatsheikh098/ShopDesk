"""Products CRUD, search, CSV import (dry-run + commit)."""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, or_, select

from app.db import get_session
from app.deps import require_csrf, require_login, require_owner
from app.models import Category, Product
from app.money import to_minor
from app.templates import templates

router = APIRouter(prefix="/products", tags=["products"])


# --- HTML pages (used by both owner and cashier) ---------------------------

@router.get("")
def list_products(
    request: Request,
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
    _user=Depends(require_login),
):
    stmt = select(Product).order_by(Product.name)
    if q:
        like = f"%{q}%"
        stmt = select(Product).where(
            or_(Product.name.like(like), Product.sku.like(like), Product.barcode.like(like))
        ).order_by(Product.name)
    products = session.exec(stmt).all()
    return templates.TemplateResponse(
        request, "products/list.html.j2", {"products": products, "q": q or ""}
    )


@router.get("/new")
def new_product_form(
    request: Request,
    session: Session = Depends(get_session),
    _user=Depends(require_owner),
):
    cats = session.exec(select(Category).order_by(Category.name)).all()
    return templates.TemplateResponse(
        request, "products/new.html.j2", {"categories": cats, "error": None}
    )


@router.post("/new", dependencies=[Depends(require_csrf), Depends(require_owner)])
def create_product(
    name: str = Form(...),
    sku: str = Form(...),
    barcode: str = Form(default=""),
    unit: str = Form(default="pcs"),
    sell_price: str = Form(...),
    cost_price: str = Form(...),
    low_stock_threshold: int = Form(default=0),
    category_id: int | None = Form(default=None),
    session: Session = Depends(get_session),
):
    name = name.strip()
    sku = sku.strip()
    barcode = (barcode or "").strip() or None
    if not name or not sku:
        raise HTTPException(status_code=400, detail="name and sku are required")
    try:
        sell = to_minor(sell_price)
        cost = to_minor(cost_price)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"invalid price: {e}") from e
    if sell < 0 or cost < 0 or low_stock_threshold < 0:
        raise HTTPException(status_code=400, detail="numbers must be non-negative")
    p = Product(
        name=name,
        sku=sku,
        barcode=barcode,
        unit=unit or "pcs",
        sell_price=sell,
        cost_price=cost,
        low_stock_threshold=low_stock_threshold,
        category_id=category_id,
    )
    session.add(p)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=f"duplicate SKU or barcode: {e.orig}") from e
    return RedirectResponse(url="/products", status_code=303)


# --- JSON: search endpoint for the POS bar ---------------------------------

@router.get("/api/search")
def api_search(
    q: str = Query(..., min_length=1),
    session: Session = Depends(get_session),
    _user=Depends(require_login),
):
    like = f"%{q}%"
    stmt = (
        select(Product)
        .where(
            or_(
                Product.name.like(like),
                Product.sku.like(like),
                Product.barcode.like(like),
            )
        )
        .where(Product.is_active == True)  # noqa: E712
        .order_by(Product.name)
        .limit(20)
    )
    rows = session.exec(stmt).all()
    return JSONResponse(
        [
            {
                "id": p.id,
                "name": p.name,
                "sku": p.sku,
                "barcode": p.barcode,
                "unit": p.unit,
                "sell_price": p.sell_price,
                "stock": p.stock,
            }
            for p in rows
        ]
    )


@router.get("/api/by-barcode/{barcode}")
def api_by_barcode(
    barcode: str,
    session: Session = Depends(get_session),
    _user=Depends(require_login),
):
    p = session.exec(select(Product).where(Product.barcode == barcode)).first()
    if not p:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "id": p.id, "name": p.name, "sku": p.sku, "barcode": p.barcode,
        "unit": p.unit, "sell_price": p.sell_price, "stock": p.stock,
    }


# --- CSV import: dry run and commit ----------------------------------------

REQUIRED_CSV_COLS = ["name", "sku", "sell_price", "cost_price"]


def _parse_csv(file_bytes: bytes) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (good_rows, bad_rows). bad_rows is a list of {row_number, errors, raw}."""
    reader = csv.DictReader(io.StringIO(file_bytes.decode("utf-8-sig")))
    if not reader.fieldnames or not all(c in reader.fieldnames for c in REQUIRED_CSV_COLS):
        return [], [{"row_number": 0, "errors": [f"missing columns; need {REQUIRED_CSV_COLS}"], "raw": {}}]
    good: list[dict[str, Any]] = []
    bad: list[dict[str, Any]] = []
    for i, row in enumerate(reader, start=1):
        errors: list[str] = []
        for c in REQUIRED_CSV_COLS:
            if not (row.get(c) or "").strip():
                errors.append(f"missing {c}")
        try:
            sell = to_minor(row.get("sell_price", "0"))
            cost = to_minor(row.get("cost_price", "0"))
        except (ValueError, TypeError) as e:
            errors.append(f"price parse: {e}")
            sell = cost = -1
        threshold_raw = row.get("low_stock_threshold", "0") or "0"
        try:
            threshold = int(threshold_raw)
        except ValueError:
            errors.append("low_stock_threshold must be int")
            threshold = -1
        if errors:
            bad.append({"row_number": i, "errors": errors, "raw": row})
        else:
            good.append(
                {
                    "name": (row.get("name") or "").strip(),
                    "sku": (row.get("sku") or "").strip(),
                    "barcode": ((row.get("barcode") or "").strip() or None),
                    "unit": (row.get("unit") or "pcs").strip() or "pcs",
                    "sell_price": sell,
                    "cost_price": cost,
                    "low_stock_threshold": threshold,
                }
            )
    return good, bad


@router.post("/import", dependencies=[Depends(require_csrf), Depends(require_owner)])
async def import_products(
    file: UploadFile = File(...),
    confirm: str = Form(default=""),
    session: Session = Depends(get_session),
):
    """CSV import.

    Without `confirm=yes`: dry run, returns JSON with the parsed rows and any
    per-row errors. With `confirm=yes`: commit only the good rows. Per-row
    integrity failures are reported in `failures`.
    """
    raw = await file.read()
    good, bad = _parse_csv(raw)
    if confirm != "yes":
        return JSONResponse(
            {
                "dry_run": True,
                "would_import": len(good),
                "errors": bad,
                "good_preview": good[:5],
            }
        )
    imported = 0
    failures: list[dict[str, Any]] = []
    for g in good:
        p = Product(
            name=g["name"],
            sku=g["sku"],
            barcode=g["barcode"],
            unit=g["unit"],
            sell_price=g["sell_price"],
            cost_price=g["cost_price"],
            low_stock_threshold=g["low_stock_threshold"],
        )
        session.add(p)
        try:
            session.flush()
            imported += 1
        except IntegrityError as e:
            session.rollback()
            failures.append({"sku": g["sku"], "error": str(e.orig)})
    session.commit()
    return JSONResponse(
        {
            "dry_run": False,
            "imported": imported,
            "failures": failures,
            "errors": bad,
        }
    )
