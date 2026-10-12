"""Generate README screenshots via Playwright.

Spins up the app on a real port, logs in, captures the login page, the
POS, the products list, and the daily report. Writes PNGs into
docs/screenshots/.

Skips if Playwright or the chromium binary is unavailable.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time

import uvicorn


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(f"playwright not available: {e}", file=sys.stderr)
        return 0

    port = _free_port()
    db = "./_screenshot.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db}"
    os.environ["APP_ENV"] = "development"
    os.environ["SECRET_KEY"] = "screenshot-secret-1234567890"
    if os.path.exists(db):
        os.remove(db)
    from app.db import create_db_and_tables

    create_db_and_tables()
    from scripts import seed  # type: ignore

    seed.main()

    config = uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)

    out = os.path.abspath("docs/screenshots")
    os.makedirs(out, exist_ok=True)
    base = f"http://127.0.0.1:{port}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1100, "height": 700})
            page = ctx.new_page()
            # Login page (no session).
            page.goto(f"{base}/login")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=f"{out}/01-login.png", full_page=True)
            # Log in via JSON API.
            r = page.request.post(
                f"{base}/api/auth/login",
                data={"username": "owner", "password": "owner123"},
            )
            assert r.status == 200, r.text()
            # POS
            page.goto(f"{base}/pos")
            page.wait_for_selector("#barcode")
            page.fill("#barcode", "8901111000012")
            page.press("#barcode", "Enter")
            page.wait_for_function(
                "() => document.querySelectorAll('#cart tbody tr').length === 1"
            )
            page.screenshot(path=f"{out}/02-pos-cart.png", full_page=True)
            # Products list
            page.goto(f"{base}/products")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=f"{out}/03-products.png", full_page=True)
            # Daily report
            page.goto(f"{base}/reports/daily")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=f"{out}/04-daily-report.png", full_page=True)
            # Settings
            page.goto(f"{base}/settings")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=f"{out}/05-settings.png", full_page=True)
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if os.path.exists(db):
            os.remove(db)
    print(f"screenshots written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
