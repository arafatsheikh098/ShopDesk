"""Auth routes: login, logout, password change."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from app.auth import (
    check_login_rate_limit,
    clear_session_cookie,
    hash_password,
    reset_login_rate_limit,
    set_session_cookie,
    verify_password,
)
from app.db import get_session
from app.deps import get_current_user, require_csrf
from app.models import User
from app.templates import templates

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html.j2", {"error": None, "user": None})


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    ip = request.client.host if request.client else "unknown"
    if not check_login_rate_limit(ip):
        raise HTTPException(status_code=429, detail="too many login attempts; try again later")
    user = session.exec(select(User).where(User.username == username)).first()
    if not user or not user.is_active or not verify_password(user.password_hash, password):
        # Show a generic error so we don't reveal whether the user exists.
        return templates.TemplateResponse(
            request, "login.html.j2", {"error": "Invalid username or password", "user": None},
            status_code=401,
        )
    reset_login_rate_limit(ip)
    response = RedirectResponse(url="/pos", status_code=303)
    set_session_cookie(response, user.id or 0)
    return response


@router.post("/logout", dependencies=[Depends(require_csrf)])
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(response)
    return response


@router.post("/password", dependencies=[Depends(require_csrf)])
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if user is None:
        raise HTTPException(status_code=401, detail="login required")
    if not verify_password(user.password_hash, current_password):
        raise HTTPException(status_code=400, detail="current password is wrong")
    if not new_password or len(new_password) < 4:
        raise HTTPException(status_code=400, detail="new password too short")
    user.password_hash = hash_password(new_password)
    session.add(user)
    session.commit()
    return RedirectResponse(url="/pos", status_code=303)


# JSON login (used by POS JS, and the smoke test script).
@router.post("/api/auth/login")
def api_login(
    request: Request,
    payload: dict,
    session: Session = Depends(get_session),
):
    ip = request.client.host if request.client else "unknown"
    if not check_login_rate_limit(ip):
        raise HTTPException(status_code=429, detail="too many login attempts")
    username = payload.get("username") or ""
    password = payload.get("password") or ""
    user = session.exec(select(User).where(User.username == username)).first()
    if not user or not user.is_active or not verify_password(user.password_hash, password):
        raise HTTPException(status_code=401, detail="invalid credentials")
    reset_login_rate_limit(ip)
    # We can't return a Set-Cookie from a JSONResponse via JSONResponse easily;
    # use a Response with a JSON body.
    from fastapi.responses import JSONResponse

    resp = JSONResponse({"ok": True, "user": {"id": user.id, "role": user.role.value}})
    set_session_cookie(resp, user.id or 0)
    return resp


@router.get("/api/auth/me")
def api_me(user: User | None = Depends(get_current_user)):
    if user is None:
        raise HTTPException(status_code=401, detail="not logged in")
    return {"id": user.id, "username": user.username, "role": user.role.value}
