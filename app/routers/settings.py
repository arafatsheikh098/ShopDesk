"""Settings page (owner only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.auth import csrf_token_for
from app.db import get_session
from app.deps import require_csrf, require_owner
from app.settings_store import effective_settings, update_settings
from app.templates import templates

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def settings_form(
    request: Request,
    session: Session = Depends(get_session),
    _user=Depends(require_owner),
):
    s = effective_settings(session)
    return templates.TemplateResponse(
        request,
        "settings.html.j2",
        {
            "settings": s,
            "csrf_token": csrf_token_for(request),
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.post("", dependencies=[Depends(require_csrf), Depends(require_owner)])
def settings_save(
    request: Request,
    shop_name: str = Form(default=""),
    shop_address: str = Form(default=""),
    shop_phone: str = Form(default=""),
    currency_symbol: str = Form(default=""),
    shop_timezone: str = Form(default=""),
    invoice_footer: str = Form(default=""),
    session: Session = Depends(get_session),
):
    update_settings(
        session,
        {
            "shop_name": shop_name.strip(),
            "shop_address": shop_address.strip(),
            "shop_phone": shop_phone.strip(),
            "currency_symbol": currency_symbol.strip() or "৳",
            "shop_timezone": shop_timezone.strip() or "Asia/Dhaka",
            "invoice_footer": invoice_footer.strip(),
        },
    )
    return RedirectResponse(url="/settings?saved=1", status_code=303)
