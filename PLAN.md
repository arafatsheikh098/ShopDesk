# PLAN.md — milestones, files, and tests

## M1 Foundation
Files to create:
- `pyproject.toml` (deps pinned)
- `.env.example`
- `app/__init__.py`
- `app/main.py` (app factory + /health)
- `app/config.py` (pydantic-settings)
- `app/db.py` (engine, session)
- `app/money.py` (integer minor units, formatting, parsing)
- `app/models/__init__.py` (re-exports)
- `app/models/user.py`, `product.py`, `category.py`, `stock_movement.py`, `customer.py`, `sale.py`, `sale_line.py`, `due_payment.py`, `sale_review.py`, `setting.py` (SQLModel entities for every feature; only fields used in tests/code are populated, but the table shape is final)
- `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_init.py`
- `app/templates/base.html.j2`
- `Dockerfile` (non-root, HEALTHCHECK)
- `docker-compose.yml` (app + postgres)
- `Makefile`
- `.github/workflows/ci.yml` (Postgres service)
- `tests/conftest.py`, `tests/test_money.py`

Tests:
- A1 `docker compose up --build` serves /health (smoke script in repo, exercised in CI)
- A2 alembic upgrade and downgrade on Postgres and SQLite
- A3 money helper never uses floats (tricky values like 0.1+0.2 style inputs)
- A4 CI is green

## M2 Auth and roles
Files to create:
- `app/auth.py` (argon2 hashing, session signing, CSRF, login rate limit)
- `app/routers/auth.py` (login, logout, password change)
- `app/deps.py` (role dependencies: `require_owner`, `require_login`, `current_user`)
- `app/templates/login.html.j2`
- `app/static/js/htmx-1.9.10.min.js` (vendored, eval-disabled CSP)
- `tests/test_auth.py` (parametrized route discovery for CSRF + session)
- `tests/test_roles.py` (parametrized owner-only route rejection)
- `scripts/create_owner.py` (CLI to create owner)
- `scripts/create_user.py` (CLI to create cashier — owner only conceptually, but in M2 we expose minimal CLI)

Tests:
- A1 parametrized test discovers all routes at runtime and proves state-changing routes need CSRF + session
- A2 owner-only routes return 403 for cashiers
- A3 rate limit and cookie flags are tested
- A4 production refuses to start with default SECRET_KEY

## M3 Catalog and stock
Files to create:
- `app/routers/categories.py`
- `app/routers/products.py` (CRUD, search, CSV import dry-run + commit)
- `app/routers/stock.py` (receive-stock, adjustment with reason, low-stock list)
- `app/templates/products/*.html.j2`, `categories/*.html.j2`, `stock/*.html.j2`
- `tests/test_catalog.py` (uniqueness, search, CSV import, dry-run, bad-row report)
- `tests/test_stock.py` (ledger invariant, low-stock, reason required, receive, concurrent decrement Postgres)

Tests:
- A1 SKU and barcode uniqueness enforced and reported clearly
- A2 CSV import: dry run changes nothing; bad rows reported; only good rows committed on confirm
- A3 stock = sum of ledger deltas for every product (invariant test)
- A4 stock never goes negative; 20 parallel attempts on stock of 5 on Postgres
- A5 cashier cannot see cost prices (rendered output test)

## M4 Sales and POS
Files to create:
- `app/sales.py` (sale number generator, transactional sale, void, due payments)
- `app/routers/pos.py` (HTML POS page)
- `app/routers/api_sales.py` (JSON endpoints)
- `app/routers/customers.py`
- `app/templates/pos.html.j2`
- `app/static/js/pos/*.js` (ES module: cart, barcode input, sync, IndexedDB queue)
- `tests/test_sales.py` (totals, discounts, percent rounding, void once, due without customer, due balance, price snapshot)
- `tests/test_sale_numbers.py` (concurrent sale number uniqueness on Postgres)

Tests:
- A1 totals, discounts, percent rounding exact (parametrized: 0, 100%, over-cap, odd)
- A2 a sale that would make any stock negative fails as a whole (no partial changes)
- A3 sale numbers unique and gap-free under concurrent sales on Postgres
- A4 void restores stock exactly once; voiding twice rejected
- A5 due sale without customer rejected; due balance math tested
- A6 price snapshot: changing product price later does not change old sale lines

## M5 Invoices and reports
Files to create:
- `app/invoices.py` (reportlab PDF generation with Noto Sans Bengali)
- `app/routers/invoices.py` (PDF download)
- `app/reports.py` (daily/monthly reports, profit, top products, dues)
- `app/routers/reports.py`
- `app/templates/reports/*.html.j2`
- `assets/fonts/NotoSansBengali-Regular.ttf` (bundled, OFL)
- `assets/fonts/OFL.txt`
- `tests/test_invoices.py` (PDF text extraction, font embedding)
- `tests/test_reports.py` (frozen time across midnight in Asia/Dhaka, profit worked example, CSV injection)

Tests:
- A1 PDF generated, opens, contains expected text, renders Bangla (text + font embedding)
- A2 daily and monthly reports correct across midnight in SHOP_TIMEZONE (frozen time)
- A3 profit = sum(line sell - line cost snapshot) * qty - discounts (worked example)
- A4 only owners can open reports
- A5 CSV export neutralizes cells starting with = + - @

## M6 Offline PWA
Files to create:
- `app/static/manifest.webmanifest`
- `app/static/icons/icon-192.png`, `icon-512.png` (simple generated PNGs)
- `app/static/sw.js` (versioned cache, safe update flow)
- `app/static/js/pos/offline.js` (IndexedDB queue, sync, pending badge, needs-review)
- `app/routers/api_sales.py` extended: idempotency key handling, price-mismatch flag, needs-review
- `tests/test_idempotency.py` (same key twice = one sale, one stock movement)
- `tests/test_offline_pwa.py` (Playwright: offline, sale, online, syncs once)
- `tests/test_sw_update.py` (version bump triggers safe update)
- `tests/test_offline_scope.py` (offline mode never exposes pages other than POS shell + cached product list)

Tests:
- A1 same idempotency key twice returns same sale, one stock movement
- A2 Playwright offline test: load POS → offline → sale → pending=1 → online → synced once → stock decreased once
- A3 queued sale with insufficient stock at sync → needs-review (nothing lost, nothing duplicated)
- A4 new deployment updates cached app shell safely (update flow test)
- A5 offline mode never exposes pages other than POS shell + cached product list

## M7 Backups, seed, settings, end-to-end tests
Files to create:
- `scripts/backup.sh` (pg_dump + sqlite3 .backup)
- `scripts/restore.sh`
- `tests/test_backup_restore.py` (wipe + restore + counts/stock match)
- `scripts/seed.py` (idempotent: grocery shop, 50 products, 3 customers)
- `tests/test_seed.py` (running twice creates no duplicates)
- `app/routers/settings.py`
- `app/templates/settings.html.j2`
- `tests/test_e2e.py` (Playwright: cashier login → barcode + Enter → finish sale → invoice PDF; owner → daily report)
- `tests/test_responsive.py` (no horizontal scroll at 375px on POS and list pages)

Tests:
- A1 restore test: back up, wipe, restore, all counts and stock totals match
- A2 running the seed twice creates no duplicates
- A3 e2e: cashier logs in, types barcode + Enter, finishes sale, downloads PDF; owner sees sale in daily report
- A4 no horizontal scroll at 375px on POS and list pages
