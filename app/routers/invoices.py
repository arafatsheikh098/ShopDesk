"""Invoice PDF download route."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import Session, select

from app.db import get_session
from app.deps import require_login
from app.invoices import render_invoice_pdf
from app.models import Customer, Sale, SaleLine

router = APIRouter(tags=["invoices"])


@router.get("/invoices/{sale_number}.pdf")
def get_invoice(
    sale_number: str,
    session: Session = Depends(get_session),
    _user=Depends(require_login),
):
    sale = session.exec(select(Sale).where(Sale.sale_number == sale_number)).first()
    if not sale:
        raise HTTPException(status_code=404, detail="sale not found")
    lines = session.exec(select(SaleLine).where(SaleLine.sale_id == sale.id)).all()
    customer_name = None
    if sale.customer_id:
        c = session.get(Customer, sale.customer_id)
        if c:
            customer_name = f"{c.name} ({c.phone})"
    pdf_bytes = render_invoice_pdf(sale, lines, customer_name)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{sale_number}.pdf"'},
    )
