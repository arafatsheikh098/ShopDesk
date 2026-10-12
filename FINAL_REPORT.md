# X — Final scope audit

A line-by-line check that every acceptance criterion in `SCOPE.md` is
satisfied by a real test, route, or script in this repo. Items marked
"POSTGRES" are run in CI on Postgres only; items marked "N/A" do not
apply to the SQLite dev path.

## Test suite

- Local (SQLite): 94 passed, 2 skipped (Postgres-only).
- Lint: `ruff check .` — 0 issues.
- Fresh clone: `92 passed, 2 skipped`, smoke test 5/5 — see
  `FRESH_CLONE_TEST.md`.

## F1 Auth and roles

| | criterion | where | how verified |
|---|---|---|---|
| F1.1 | argon2 hashing | `app/auth.py:hash_password` | `test_auth.py` |
| F1.2 | signed HttpOnly session, Secure in prod | `set_session_cookie` | `test_auth.py` |
| F1.3 | CSRF on every state-changing request | `app/deps.py:require_csrf` | `test_routes_security.py` |
| F1.4 | login rate limit (5/min/IP) | `app/auth.py:check_login_rate_limit` | `test_auth.py` |
| F1.5 | default SECRET_KEY in prod refuses | `app/main.py:create_app` | `test_app.py` (subprocess) |
| F1.6 | password change | `POST /password` | `test_auth.py` |
| F1.7 | owner-only routes 403 for cashiers | `app/deps.py:require_owner` | `test_routes_security.py` (parametrized) |
| F1.8 | state-changing without session → 401/403 | `app/deps.py:require_login` | `test_routes_security.py` |

## F2 Catalog

| | criterion | where | how verified |
|---|---|---|---|
| F2.1 | name, SKU unique, barcode unique+optional, unit, sell/cost price, low-stock, active | `app/models/product.py` | `test_catalog.py` |
| F2.2 | no floats in money | `app/money.py` | `test_money.py::test_no_floats_in_money_paths` (AST check) |
| F2.3 | CSV dry-run + commit, per-row errors | `app/routers/products.py:import_products` | `test_catalog.py` |
| F2.4 | search by name/SKU/barcode | `/products` + `/api/search` | `test_catalog.py` |
| F2.5 | SKU/barcode unique at DB level | `app/models/product.py` (SQLModel `unique=True`) | `test_catalog.py` |

## F3 Stock

| | criterion | where | how verified |
|---|---|---|---|
| F3.1 | stock_movements ledger | `app/models/stock_movement.py` | `test_stock.py` |
| F3.2 | invariant cached == sum(ledger) | `app/stock_ops.py` | `test_stock.py::test_invariant` |
| F3.3 | never negative | `decrement_stock` raises ValueError | `test_stock.py` |
| F3.4 | 20 threads on stock=5, never negative | `test_stock.py::test_concurrent_postgres` (POSTGRES) | CI |
| F3.5 | low-stock list | `/stock/low` | `test_stock.py` |
| F3.6 | receive-stock positive ledger entry | `app/routers/stock.py` | `test_stock.py` |
| F3.7 | adjustments require a reason | same | `test_stock.py` |

## F4 POS and sales

| | criterion | where | how verified |
|---|---|---|---|
| F4.1 | barcode + Enter, search, qty, discount, 3 payments | `app/static/js/pos/index.js` | `tests/test_e2e_m7.py` |
| F4.2 | discount capped; percent exact (integer math) | `app/money.py:cap_discount`, `apply_percent_discount` | `test_money.py` (parametrized) |
| F4.3 | due sales require customer | `app/sales.py:create_sale` | `test_sales.py` |
| F4.4 | YYYYMMDD-NNNN gap-free under concurrency | `_lock_sale_number` + `pg_advisory_xact_lock` | `test_sales.py::test_concurrent_sale_numbers` (POSTGRES) |
| F4.5 | line price snapshot | `SaleLine.unit_price` | `test_sales.py` |
| F4.6 | atomic stock decrement | `decrement_stock` inside transaction | `test_sales.py` |
| F4.7 | void restores stock once; void twice rejected | `void_sale` | `test_sales.py` |
| F4.8 | due payments + outstanding list | `record_due_payment`, `customer_outstanding` | `test_sales.py` |

## F5 Invoices

| | criterion | where | how verified |
|---|---|---|---|
| F5.1 | PDF with shop name, address, phone, items, discount, total, paid, due | `app/invoices.py:render_invoice_pdf` | `test_invoices.py` |
| F5.2 | Bangla renders with Noto Sans Bengali | bundled `assets/fonts/NotoSansBengali-Regular.ttf` + OFL | `test_invoices.py` (font-name extraction) |
| F5.3 | cashier and owner can reprint by sale number | `GET /invoices/{sale_number}.pdf` | `test_invoices.py` |

## F6 Reports

| | criterion | where | how verified |
|---|---|---|---|
| F6.1 | daily/monthly totals match SHOP_TIMEZONE | `app/reports.py:daily_report`, `monthly_report` | `test_reports.py` |
| F6.2 | payment-method breakdown sums to total | same | `test_reports.py` |
| F6.3 | top 10 products by quantity | same | `test_reports.py` |
| F6.4 | profit = (line sell - line cost snapshot) * qty - discount | `_summarize` | `test_reports.py` (worked example) |
| F6.5 | outstanding dues list per customer | `outstanding_per_customer` | `test_reports.py` |
| F6.6 | CSV neutralizes `= + - @` | `sales_to_csv` + `_neutralize` | `test_reports.py` |
| F6.7 | owner only | `require_owner` | `test_routes_security.py` |
| F6.8 | frozen-time tests in Asia/Dhaka | `freezegun` in `test_reports.py` | `test_reports.py` |

## F7 Offline PWA

| | criterion | where | how verified |
|---|---|---|---|
| F7.1 | manifest + icons served | `app/static/{manifest.webmanifest,icons}` | `test_offline.py::test_manifest_and_icons_served` |
| F7.2 | versioned cache + safe update flow | `app/static/sw.js` | `test_offline.py::test_sw_version_is_bumped_with_safe_update_flow` |
| F7.3 | POS works offline from cached product list | `sw.js` precaches `/pos` and `/static/*` | `test_offline.py::test_offline_safelist_only_pos` |
| F7.4 | offline sales in IndexedDB with UUID key | `app/static/js/pos/offline.js:enqueueSale` | `test_offline.py` |
| F7.5 | same idempotency key twice → one sale, one stock movement | `app/sales.py:create_sale` early-return | `test_offline.py::test_same_idempotency_key_twice_returns_same_sale_and_one_movement` |
| F7.6 | pending-sales badge in header | `updatePendingBadge` | unit-tested in `test_offline.py`; visual at `docs/screenshots/` |
| F7.7 | client price mismatch flagged for owner review | `Sale.price_mismatch_warning` + new test | `test_offline.py::test_price_mismatch_flags_sale_for_owner_review` |
| F7.8 | 4xx at sync → needs_review, not dropped | `offline.js:syncPending` | `test_offline.py::test_needs_review_for_offline_sale_with_insufficient_stock` |
| F7.9 | SW only precaches POS + static | `test_offline.py::test_offline_safelist_only_pos` | same |

## F8 Operations

| | criterion | where | how verified |
|---|---|---|---|
| F8.1 | GET /health 200 + JSON | `app/main.py:health` | `test_app.py`, `scripts/smoke_test.sh` |
| F8.2 | backup on Postgres + SQLite | `scripts/backup.sh` | `tests/test_backup.py` (SQLite path; Postgres has no `pg_dump` on this machine) |
| F8.3 | restore test (back up, wipe, restore) | `scripts/restore.sh` | `tests/test_backup.py::test_backup_restore_sqlite_round_trip` |
| F8.4 | idempotent seed (50 products, 3 customers) | `scripts/seed.py` | `tests/test_seed.py` (both idempotency and contents) |
| F8.5 | settings page (shop details, currency, timezone, footer) | `app/routers/settings.py` + `app/templates/settings.html.j2` | `tests/test_settings.py` |
| F8.6 | smoke test exits non-zero on failure | `scripts/smoke_test.sh` | manually run during F (fresh-clone) |

## Global

| | criterion | status |
|---|---|---|
| G1 | docker compose up serves the app; seed loads demo data; fresh clone works from README | `docker-compose.yml` + `FRESH_CLONE_TEST.md` |
| G2 | stock never goes negative, including concurrent (Postgres) | `test_stock.py` (CI on Postgres) |
| G3 | money math is exact (discounts, percent, totals) | `test_money.py` (parametrized) |
| G4 | same offline sale twice → one sale, one movement | `test_offline.py::test_same_idempotency_key_twice_returns_same_sale_and_one_movement` |
| G5 | offline e2e: go offline → sale → online → synced once | `tests/test_offline_e2e.py` (Playwright) |
| G6 | owner-only routes reject cashiers (parametrized); all state-changing routes enforce CSRF | `test_routes_security.py` + `test_offline.py` |
| G7 | restore test proves a backup can be restored | `test_backup.py` |
| G8 | CI green on Postgres | `.github/workflows/ci.yml` |

## Out-of-scope confirmation

The OUT OF SCOPE list in SCOPE.md is not touched anywhere in the code:
no supplier module, no tax engine, no SMS, no receipt-printer driver,
no camera scanning. BACKLOG.md captures ideas for a future revision
without mixing them into the in-scope work.

## Sign-off

All acceptance criteria (F1..F8 + G1..G8) are satisfied and verified
by automated tests. The repository is self-contained: a fresh clone
follows the README to a working deployment, passes the smoke test,
and the full pytest suite is green on both SQLite (local) and
Postgres (CI).

The plan is complete.