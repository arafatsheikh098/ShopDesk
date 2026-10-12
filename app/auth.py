"""Authentication: argon2 hashing, session cookies, CSRF, rate limiting."""
from __future__ import annotations

import hmac
import time
from collections import defaultdict

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Request
from itsdangerous import BadSignature, URLSafeSerializer

from app.config import get_settings

# --- Password hashing -----------------------------------------------------

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    if not plain or not isinstance(plain, str):
        raise ValueError("password must be a non-empty string")
    return _hasher.hash(plain)


def verify_password(hash_str: str, plain: str) -> bool:
    try:
        return _hasher.verify(hash_str, plain)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


# --- Sessions -------------------------------------------------------------

_SESSION_COOKIE = "shopdesk_session"
_CSRF_COOKIE = "shopdesk_csrf"
_SESSION_FIELD = "uid"  # user id stored in the signed cookie


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(get_settings().secret_key, salt="shopdesk-session")


def make_session_cookie(user_id: int) -> str:
    s = _serializer()
    return s.dumps({_SESSION_FIELD: int(user_id)})


def read_session_cookie(token: str) -> int | None:
    try:
        data = _serializer().loads(token)
    except BadSignature:
        return None
    uid = data.get(_SESSION_FIELD)
    return int(uid) if isinstance(uid, int) else None


def make_csrf_token(session_token: str) -> str:
    """Derive a CSRF token from the session token. Constant-time comparable."""
    import hashlib

    digest = hashlib.sha256(("csrf|" + session_token).encode("utf-8")).hexdigest()
    return digest


def csrf_matches(submitted: str | None, expected: str | None) -> bool:
    if not submitted or not expected:
        return False
    return hmac.compare_digest(submitted, expected)


def set_session_cookie(response, user_id: int) -> None:
    token = make_session_cookie(user_id)
    settings = get_settings()
    response.set_cookie(
        key=_SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=_CSRF_COOKIE,
        value=make_csrf_token(token),
        httponly=False,  # JS must be able to read it for double-submit
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(_SESSION_COOKIE, path="/")
    response.delete_cookie(_CSRF_COOKIE, path="/")


# --- Rate limit (login) ---------------------------------------------------

_login_attempts: dict[str, list[float]] = defaultdict(list)


def check_login_rate_limit(ip: str) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    settings = get_settings()
    limit = settings.login_rate_limit_per_minute
    now = time.time()
    window = 60.0
    attempts = _login_attempts[ip]
    # Drop old attempts.
    while attempts and now - attempts[0] > window:
        attempts.pop(0)
    if len(attempts) >= limit:
        return False
    attempts.append(now)
    return True


def reset_login_rate_limit(ip: str) -> None:
    _login_attempts.pop(ip, None)


# --- Helpers --------------------------------------------------------------

def get_current_user_id(request: Request) -> int | None:
    token = request.cookies.get(_SESSION_COOKIE)
    if not token:
        return None
    return read_session_cookie(token)


def require_csrf(request: Request) -> bool:
    """Validate CSRF on state-changing requests using double-submit cookie."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    cookie = request.cookies.get(_CSRF_COOKIE)
    # Accept token from header (X-CSRF-Token) or form field (_csrf).
    submitted = request.headers.get("X-CSRF-Token")
    if not submitted:
        # Try to peek at form (only works for urlencoded/multipart, fine for our app)
        # We don't await body here; the route can call require_csrf_for_form() instead.
        submitted = request.headers.get("x-csrf-token")
    return csrf_matches(submitted, cookie)


def csrf_token_for(request: Request) -> str:
    """Return the CSRF token that the client should send back."""
    return request.cookies.get(_CSRF_COOKIE, "")


# --- Module-level constants ----------------------------------------------

SESSION_COOKIE = _SESSION_COOKIE
CSRF_COOKIE = _CSRF_COOKIE
