"""Sales API and POS HTML page."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_user, require_csrf, require_login
from app.models import Category, Customer, PaymentMethod, Product, Sale, SaleLine, User
from app.sales import create_sale, customer_outstanding, record_due_payment, void_sale
from app.templates import templates

router = APIRouter(tags=["sales"])


# --- HTML: POS page --------------------------------------------------------

@router.get("/pos", response_class=HTMLResponse)
def pos_page(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_login),
):
    products = session.exec(
        select(Product).where(Product.is_active == True).order_by(Product.name)  # noqa: E712
    ).all()
    categories = session.exec(select(Category).order_by(Category.name)).all()
    cat_map = {c.id: c.name for c in categories if c.id is not None}
    return templates.TemplateResponse(
        request,
        "pos.html.j2",
        {
            "products": [
                {
                    "id": p.id,
                    "name": p.name,
                    "sku": p.sku,
                    "barcode": p.barcode,
                    "unit": p.unit,
                    "sell_price": p.sell_price,
                    "stock": p.stock,
                    "category": cat_map.get(p.category_id, "General"),
                }
                for p in products
            ],
            "categories": [{"id": c.id, "name": c.name} for c in categories],
            "csrf_token": request.cookies.get("shopdesk_csrf", ""),
            "user": user,
        },
    )


# --- JSON: create a sale (used by POS and offline sync) --------------------

@router.post("/api/sales", dependencies=[Depends(require_csrf)])
def api_create_sale(
    payload: dict[str, Any],
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if user is None:
        raise HTTPException(status_code=401, detail="login required")
    idempotency_key = payload.get("idempotency_key")
    payment_method = PaymentMethod(payload.get("payment_method", "cash"))
    try:
        sale = create_sale(
            session,
            user=user,
            lines=payload.get("lines") or [],
            discount_minor=int(payload.get("discount_minor") or 0),
            discount_percent=int(payload.get("discount_percent") or 0),
            payment_method=payment_method,
            paid_minor=payload.get("paid_minor"),
            customer_id=payload.get("customer_id"),
            customer_name=payload.get("customer_name"),
            customer_phone=payload.get("customer_phone"),
            idempotency_key=idempotency_key,
        )
    except HTTPException:
        # Re-raise as-is for client visibility
        raise
    return JSONResponse(
        {
            "id": sale.id,
            "sale_number": sale.sale_number,
            "subtotal": sale.subtotal,
            "discount": sale.discount,
            "total": sale.total,
            "paid": sale.paid,
            "due": sale.due,
            "status": sale.status.value,
            "price_mismatch_warning": sale.price_mismatch_warning,
        }
    )


# --- Void (owner-only) -----------------------------------------------------

@router.post("/api/sales/{sale_id}/void", dependencies=[Depends(require_csrf)])
def api_void_sale(
    sale_id: int,
    payload: dict[str, Any],
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if user is None:
        raise HTTPException(status_code=401, detail="login required")
    if user.role.value != "owner":
        raise HTTPException(status_code=403, detail="only owners can void sales")
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")
    sale = void_sale(session, sale_id=sale_id, user=user, reason=reason)
    return {"id": sale.id, "sale_number": sale.sale_number, "status": sale.status.value}


# --- Lookup sale by number (for invoice reprint) ---------------------------

@router.get("/api/sales/{sale_number}")
def api_get_sale(
    sale_number: str,
    session: Session = Depends(get_session),
    _user=Depends(require_login),
):
    sale = session.exec(select(Sale).where(Sale.sale_number == sale_number)).first()
    if not sale:
        raise HTTPException(status_code=404, detail="sale not found")
    lines = session.exec(select(SaleLine).where(SaleLine.sale_id == sale.id)).all()
    return {
        "id": sale.id,
        "sale_number": sale.sale_number,
        "created_at": sale.created_at.isoformat(),
        "subtotal": sale.subtotal,
        "discount": sale.discount,
        "total": sale.total,
        "paid": sale.paid,
        "due": sale.due,
        "payment_method": sale.payment_method.value,
        "status": sale.status.value,
        "lines": [
            {
                "product_name": line.product_name,
                "unit_price": line.unit_price,
                "quantity": line.quantity,
                "line_total": line.line_total,
            }
            for line in lines
        ],
    }


# --- Customers: list and search (cashier and owner) -----------------------

@router.get("/api/customers")
def api_customers(
    q: str | None = None,
    session: Session = Depends(get_session),
    _user=Depends(require_login),
):
    stmt = select(Customer).order_by(Customer.name)
    if q:
        like = f"%{q}%"
        stmt = select(Customer).where(Customer.name.like(like)).order_by(Customer.name)
    rows = session.exec(stmt).all()
    return [
        {"id": c.id, "name": c.name, "phone": c.phone, "outstanding": customer_outstanding(session, c.id)}
        for c in rows
    ]


@router.post("/api/customers", dependencies=[Depends(require_csrf)])
def api_create_customer(
    payload: dict[str, Any],
    session: Session = Depends(get_session),
    _user=Depends(require_login),
):
    name = (payload.get("name") or "").strip()
    phone = (payload.get("phone") or "").strip()
    if not name or not phone:
        raise HTTPException(status_code=400, detail="name and phone required")
    c = session.exec(select(Customer).where(Customer.phone == phone)).first()
    if c:
        c.name = name
        session.add(c)
        session.commit()
        return {"id": c.id, "name": c.name, "phone": c.phone}
    c = Customer(name=name, phone=phone)
    session.add(c)
    session.commit()
    return {"id": c.id, "name": c.name, "phone": c.phone}


# --- Due payments (owner) --------------------------------------------------

@router.post("/api/due-payments", dependencies=[Depends(require_csrf)])
def api_due_payment(
    payload: dict[str, Any],
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if user is None:
        raise HTTPException(status_code=401, detail="login required")
    cust_id = int(payload.get("customer_id") or 0)
    amount = int(payload.get("amount_minor") or 0)
    if not cust_id or amount <= 0:
        raise HTTPException(status_code=400, detail="customer_id and positive amount_minor required")
    p = record_due_payment(
        session,
        customer_id=cust_id,
        amount_minor=amount,
        user=user,
        note=payload.get("note"),
    )
    return {"id": p.id, "amount": p.amount, "outstanding": customer_outstanding(session, cust_id)}
