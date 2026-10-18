"""Stock: receive stock, adjustment with reason, low-stock list."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_user, require_csrf, require_login, require_owner
from app.models import Product, StockMovement, StockReason, User
from app.stock_ops import increment_stock
from app.templates import templates

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("")
def list_stock(
    request: Request,
    session: Session = Depends(get_session),
    _user=Depends(require_login),
):
    products = session.exec(select(Product).order_by(Product.name)).all()
    return templates.TemplateResponse(
        request, "stock/list.html.j2", {"products": products, "user": _user}
    )


@router.get("/low")
def low_stock(
    request: Request,
    session: Session = Depends(get_session),
    _user=Depends(require_owner),
):
    rows = session.exec(select(Product).where(Product.stock <= Product.low_stock_threshold)).all()
    return templates.TemplateResponse(
        request, "stock/low.html.j2", {"products": rows, "user": _user}
    )


@router.post("/receive", dependencies=[Depends(require_csrf), Depends(require_owner)])
def receive_stock(
    product_id: int = Form(...),
    quantity: int = Form(...),
    note: str = Form(default=""),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be positive")
    p = session.get(Product, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="product not found")
    increment_stock(
        session,
        product_id=product_id,
        quantity=quantity,
        reason=StockReason.PURCHASE,
        reason_text=note or None,
        user_id=user.id if user else None,
    )
    session.commit()
    return RedirectResponse(url="/stock", status_code=303)


@router.post("/adjust", dependencies=[Depends(require_csrf), Depends(require_owner)])
def adjust_stock(
    product_id: int = Form(...),
    delta: int = Form(...),
    reason_text: str = Form(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    reason_text = (reason_text or "").strip()
    if not reason_text:
        raise HTTPException(status_code=400, detail="a reason is required for adjustments")
    if delta == 0:
        raise HTTPException(status_code=400, detail="delta must be non-zero")
    p = session.get(Product, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="product not found")
    if p.stock + delta < 0:
        raise HTTPException(
            status_code=400,
            detail=f"adjustment would make stock negative (current={p.stock}, delta={delta})",
        )
    increment_stock(
        session,
        product_id=product_id,
        quantity=abs(delta),
        reason=StockReason.ADJUSTMENT,
        reason_text=reason_text,
        user_id=user.id if user else None,
    ) if delta > 0 else _decrement_for_adjust(session, product_id, abs(delta), reason_text, user)
    session.commit()
    return RedirectResponse(url="/stock", status_code=303)


def _decrement_for_adjust(session: Session, product_id: int, qty: int, reason_text: str, user):
    from app.stock_ops import decrement_stock

    decrement_stock(
        session,
        product_id=product_id,
        quantity=qty,
        reason=StockReason.ADJUSTMENT,
        user_id=user.id if user else None,
    )
    # Attach the reason text to the latest movement.
    mv = session.exec(
        __import__("sqlmodel").select(StockMovement)
        .where(StockMovement.product_id == product_id)
        .order_by(StockMovement.id.desc())
    ).first()
    if mv is not None:
        mv.reason_text = reason_text
        session.add(mv)


# --- low-level helper used by sales logic (M4 will import) -----------------

def product_or_404(session: Session, product_id: int) -> Product:
    p = session.get(Product, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="product not found")
    return p
