"""Read/write shop settings stored in the generic Setting key/value table.

These values are read at request time by templates (and the invoice PDF) so
that the owner can change them from the UI without restarting the server.
"""
from __future__ import annotations

from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.models import Setting

# Keys that map 1:1 onto Settings fields. Anything else is ignored.
_SETTING_KEYS = (
    "shop_name",
    "shop_address",
    "shop_phone",
    "currency_symbol",
    "shop_timezone",
    "invoice_footer",
)


def load_db_overrides(session: Session) -> dict[str, str]:
    """Return all settings keys/values currently in the DB (only known keys)."""
    rows = session.exec(
        select(Setting).where(Setting.key.in_(_SETTING_KEYS))
    ).all()
    return {r.key: r.value for r in rows}


def effective_settings(session: Session) -> Settings:
    """Return a Settings object with DB overrides applied on top of env."""
    s = get_settings()
    overrides = load_db_overrides(session)
    if not overrides:
        return s
    # Build a fresh Settings instance with overrides spread in. Use
    # model_construct so pydantic-settings doesn't re-read the environment
    # and clobber the values we just spread in.
    fields = {
        "app_env": s.app_env,
        "secret_key": s.secret_key,
        "database_url": s.database_url,
        "login_rate_limit_per_minute": s.login_rate_limit_per_minute,
    }
    for k in _SETTING_KEYS:
        # Environment value wins if the DB row is empty; otherwise DB wins.
        env_val = getattr(s, k, "")
        fields[k] = overrides.get(k) or env_val
    return Settings.model_construct(**fields)


def update_settings(session: Session, values: dict[str, str]) -> None:
    """Upsert the given key/value pairs into the settings table."""
    for k, v in values.items():
        if k not in _SETTING_KEYS:
            continue
        row = session.get(Setting, k)
        if row is None:
            session.add(Setting(key=k, value=v or ""))
        else:
            row.value = v or ""
    session.commit()
