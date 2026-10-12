"""FastAPI app factory."""
from __future__ import annotations

import os
import sys

from fastapi import FastAPI

from app.config import DEFAULT_SECRET_KEY, get_settings
from app.db import create_db_and_tables


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.is_production and settings.secret_key == DEFAULT_SECRET_KEY:
        # Refuse to boot in production with the default secret.
        print("FATAL: default SECRET_KEY in production. Refusing to start.", file=sys.stderr)
        raise SystemExit(2)

    app = FastAPI(title="ShopDesk", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "shopdesk"}

    @app.on_event("startup")
    def _startup() -> None:
        create_db_and_tables()

    # Mount static files (manifest, icons, service worker, JS, CSS).
    from fastapi.staticfiles import StaticFiles

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Mount routers from app.routers (no-op until later milestones add entries).
    from app.routers import mount_routers

    mount_routers(app)

    return app


# Eagerly build the default `app` for `uvicorn app.main:app`. The
# production-secret guard runs here; tests must set APP_ENV=development
# (or a real SECRET_KEY) before importing this module.
app = create_app()
