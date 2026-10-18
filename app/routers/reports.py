"""Reports routes (owner only)."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlmodel import Session, select

from app.db import get_session
from app.deps import require_owner
from app.models import Customer, Sale, SaleLine
from app.reports import daily_report, monthly_report, outstanding_per_customer, sales_to_csv
from app.templates import templates

router = APIRouter(prefix="/reports", tags=["reports"])


def _today_local() -> date:
    from app.config import get_settings

    return datetime.now(ZoneInfo(get_settings().shop_timezone)).date()


@router.get("/daily", response_class=HTMLResponse)
def daily(
    request: Request,
    d: date | None = Query(default=None),
    session: Session = Depends(get_session),
    _user=Depends(require_owner),
):
    day = d or _today_local()
    report = daily_report(session, day)
    return templates.TemplateResponse(
        request, "reports/daily.html.j2", {"day": day, "report": report, "user": _user}
    )


@router.get("/monthly", response_class=HTMLResponse)
def monthly(
    request: Request,
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    session: Session = Depends(get_session),
    _user=Depends(require_owner),
):
    today = _today_local()
    y = year or today.year
    m = month or today.month
    report = monthly_report(session, y, m)
    return templates.TemplateResponse(
        request, "reports/monthly.html.j2", {"year": y, "month": m, "report": report, "user": _user}
    )


@router.get("/dues", response_class=HTMLResponse)
def dues(
    request: Request,
    session: Session = Depends(get_session),
    _user=Depends(require_owner),
):
    rows = outstanding_per_customer(session)
    return templates.TemplateResponse(request, "reports/dues.html.j2", {"rows": rows, "user": _user})


@router.get("/export.csv")
def export_csv(
    session: Session = Depends(get_session),
    _user=Depends(require_owner),
):
    sales = list(session.exec(select(Sale)).all())
    lines_by_sale: dict[int, list[SaleLine]] = {}
    for s in sales:
        ls = list(session.exec(select(SaleLine).where(SaleLine.sale_id == s.id)).all())
        lines_by_sale[s.id or 0] = ls
    # Annotate customer name on each sale
    for s in sales:
        if s.customer_id:
            c = session.get(Customer, s.customer_id)
            s._customer_name = c.name if c else ""
        else:
            s._customer_name = ""
    body = sales_to_csv(sales, lines_by_sale)
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sales.csv"'},
    )
