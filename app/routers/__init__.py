"""Routers package (mounted in main.py)."""

from __future__ import annotations

from fastapi import FastAPI

# Modules register themselves into this list; mount order is irrelevant for
# FastAPI since routes are matched by full path.
_router_modules: list[str] = []


def register(name: str) -> None:
    """Register a router module to be mounted on app startup."""
    if name not in _router_modules:
        _router_modules.append(name)


def mount_routers(app: FastAPI) -> None:
    """Import each registered router module and include its `router`."""
    import importlib

    for name in _router_modules:
        mod = importlib.import_module(name)
        if hasattr(mod, "router"):
            app.include_router(mod.router)
