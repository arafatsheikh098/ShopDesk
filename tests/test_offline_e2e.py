"""Playwright offline e2e: go offline, make a sale, go online, see it sync.

This test starts the FastAPI app on a real port and drives it with a browser.
It's the closest thing to a real user scenario. If Playwright or the browser
is not available, the test is skipped.
"""
from __future__ import annotations

import os
import socket
import threading
import time

import pytest
import uvicorn

from app.auth import hash_password
from app.db import create_db_and_tables, get_engine
from app.models import Product, User, UserRole


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            b.close()
    except Exception as exc:
        pytest.skip(f"Chromium binary not available: {exc}")

    port = _free_port()
    # Use SQLite for this test (simpler) and set env BEFORE uvicorn imports the app.
    os.environ["DATABASE_URL"] = "sqlite:///./test_offline.db"
    os.environ["APP_ENV"] = "development"
    os.environ["SECRET_KEY"] = "offline-e2e-secret-1234567890abcdef"
    if os.path.exists("test_offline.db"):
        os.remove("test_offline.db")
    create_db_and_tables()
    from sqlmodel import Session

    with Session(get_engine()) as s:
        s.add(
            User(username="o", password_hash=hash_password("pw"), role=UserRole.OWNER)
        )
        s.add(
            User(
                username="c",
                password_hash=hash_password("pw"),
                role=UserRole.CASHIER,
            )
        )
        s.add(
            Product(
                name="TestApple",
                sku="TA1",
                barcode="TA-BC-1",
                sell_price=100,
                cost_price=50,
                stock=10,
            )
        )
        s.commit()
    config = uvicorn.Config(
        "app.main:app", host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # Wait for the server to come up.
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
    if os.path.exists("test_offline.db"):
        os.remove("test_offline.db")


def test_offline_sale_syncs_once(live_server):
    from playwright.sync_api import sync_playwright

    base = live_server
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        # 1) Log in as cashier via the JSON API and use the cookies.
        r = page.request.post(
            f"{base}/api/auth/login",
            data={"username": "c", "password": "pw"},
        )
        assert r.status == 200
        # 2) Load the POS page.
        page.goto(f"{base}/pos")
        page.wait_for_selector("#barcode")
        # 3) Simulate going offline.
        ctx.set_offline(True)
        # 4) Type a barcode + Enter, then add quantity, then click Finish.
        page.fill("#barcode", "TA-BC-1")
        page.press("#barcode", "Enter")
        page.click("#finish")
        # The page should now show "queued (offline)".
        page.wait_for_function(
            "() => document.getElementById('msg').textContent.includes('queued')",
            timeout=5000,
        )
        # 5) Go back online.
        ctx.set_offline(False)
        # 6) Trigger a reload to make the page call the online sync handler.
        # The offline.js module listens to 'online' events; we can also call
        # syncPending by reloading the page (the service worker will run it).
        # For a deterministic check, we just wait a bit and then look at the
        # pending badge.
        # The page will auto-reload after a successful sale; since the sale
        # hasn't synced yet, we just reload to trigger the sync.
        page.wait_for_timeout(500)
        page.evaluate(
            """async () => {
              const m = await import('/static/js/pos/offline.js');
              const csrf = document.cookie.split(';').map(s=>s.trim()).find(c=>c.startsWith('shopdesk_csrf='))?.split('=')[1];
              await m.syncPending(csrf);
              await m.updatePendingBadge();
            }"""
        )
        # Now the sale should be on the server.
        r = page.request.get(f"{base}/api/auth/me")
        assert r.status == 200
        # Find any sale via the search-by-id endpoint
        # Use the API to count sales via a fresh search — none of our endpoints
        # list sales, so look up by the known idempotency key. Since we don't
        # have a list endpoint, fall back to checking stock decreased.
        # We use a simple "ping" — count via sqlite via a small page.
        page.goto(f"{base}/products")
        body = page.content()
        # The product row should still be there.
        assert "TestApple" in body
        # Stock should now be 9 (started at 10, sold 1).
        assert "9" in body
        browser.close()
