"""Dependencies for FastAPI routes: current user, role checks, CSRF guard."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from app.auth import CSRF_COOKIE, csrf_matches, get_current_user_id
from app.db import get_session
from app.models import User, UserRole


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> User | None:
    uid = get_current_user_id(request)
    if uid is None:
        return None
    user = session.get(User, uid)
    if not user or not user.is_active:
        return None
    return user


def require_login(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
    return user


def require_owner(user: User = Depends(require_login)) -> User:
    if user.role != UserRole.OWNER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner required")
    return user


async def require_csrf(request: Request) -> None:
    """CSRF guard. Raises 403 if missing or wrong. GET/HEAD/OPTIONS are exempt.

    Accepts the token from the X-CSRF-Token header (JSON APIs) or from the
    `_csrf` form field (HTML forms). Forms must include the hidden input.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    expected = request.cookies.get(CSRF_COOKIE)
    submitted = request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token")
    if not submitted and request.headers.get("content-type", "").startswith(
        ("application/x-www-form-urlencoded", "multipart/form-data")
    ):
        # Peek at the form to read _csrf. FastAPI re-parses the body later.
        try:
            form = await request.form()
            submitted = form.get("_csrf")  # type: ignore[union-attr]
        except Exception:
            submitted = None
    if not csrf_matches(submitted, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf token missing or wrong")
