# SCOPE.md — the contract (never edited after initial creation)

## IN SCOPE

F1 Auth and roles: owner and cashier. Owner-only: cost prices, profit, reports, users, stock adjustments, voids, settings. Cashier: POS, view products and stock, reprint invoices. argon2 passwords, signed session cookies, CSRF on all state-changing requests, login rate limit, owner created by CLI or from env on first start, password change.

F2 Catalog: categories; products (name, SKU unique, barcode unique and optional, unit, sell price, cost price, low-stock threshold, active flag). ALL money is stored as integer minor units (paisa), never floats. CSV import of products with a dry run and a row-level error report. Search by name, SKU or barcode.

F3 Stock: a stock_movements ledger (product, delta, reason: opening/purchase/sale/void/adjustment, reference, user, timestamp); product.stock is a cached value updated in the SAME transaction; stock can never go negative; low-stock list; "receive stock" form; adjustments require a reason.

F4 POS and sales: cart; barcode input field that works with USB scanners (they type digits + Enter); search; quantity editing; discount (fixed amount or percent, capped at the subtotal); payment method (cash, mobile wallet, due); customer (name + phone, required for due sales); sale number YYYYMMDD-NNNN, per day, gap-free and unique under concurrency; price snapshot on every line; transactional stock decrement; void sale (owner only, with reason, restores stock); record due payments and list customers with outstanding balances.

F5 Invoices: PDF per sale (reportlab) with shop name, address, phone, items, discount, total, paid and due; Bangla text must render correctly using a bundled OFL-licensed Noto Sans Bengali font (license file kept).

F6 Reports (owner only): daily and monthly sales totals, payment-method breakdown, top 10 products, profit (sell minus cost snapshot), outstanding dues; CSV export; day and month boundaries in SHOP_TIMEZONE (default Asia/Dhaka).

F7 Offline POS (PWA): installable (manifest and icons); service worker caches the app shell with a versioned cache and a safe update flow; the POS screen works offline from a cached product list; sales made offline are stored in IndexedDB with a client-generated UUID idempotency key and synced when the connection returns; POST /api/sales is idempotent (same key twice returns the original sale); the UI shows a pending-sales badge; unit prices for offline-synced sales come from the client (the customer was already charged) and any mismatch with the current price is flagged for owner review; a sale that cannot be accepted at sync (for example insufficient stock) goes to a "needs review" list and is never silently dropped and never duplicated.

F8 Operations: GET /health; backup script (pg_dump for Postgres, sqlite3 .backup for SQLite) with scripts/restore.sh and a restore test; idempotent demo seed (grocery shop, 50 products, 3 customers); settings page (shop details, currency symbol, timezone, invoice footer).

## OUT OF SCOPE

Multi-shop, suppliers and purchase orders, returns other than void, taxes/VAT, camera-based barcode scanning, payment gateway integration, receipt-printer drivers, accounting, SMS, translations of the UI, desktop app, anything not listed above.

## ALLOWED STACK

Python 3.12; FastAPI; uvicorn; SQLModel; Alembic; psycopg[binary]; pydantic-settings; Jinja2; python-multipart; argon2-cffi; reportlab; vendored HTMX (eval disabled); vanilla JavaScript (ES modules) with IndexedDB and a service worker; bundled Noto Sans Bengali font file; pytest, pytest-playwright, httpx, freezegun; ruff; Docker; GitHub Actions.

## ACCEPTANCE CRITERIA

### F1 Auth and roles
F1.1 argon2 password hashing is used; passwords are never stored in plaintext.
F1.2 session cookies are signed and HttpOnly; Secure flag in production.
F1.3 CSRF token is required on every state-changing request; missing/wrong token returns 403.
F1.4 login is rate-limited (e.g. 5 attempts per minute per IP).
F1.5 owner account is created by CLI or env on first start; default SECRET_KEY in production causes startup refusal.
F1.6 password change is available to logged-in users.
F1.7 owner-only routes return 403 for cashiers (parametrized over all owner-only routes).
F1.8 a state-changing request without a session returns 401/403.

### F2 Catalog
F2.1 product name, SKU (unique), barcode (unique, optional), unit, sell price, cost price, low-stock threshold, active flag are stored.
F2.2 all money fields are integer minor units (paisa); a test proves no floats are used.
F2.3 CSV import has dry-run and commit modes; bad rows are reported per row; only good rows are committed.
F2.4 search by name, SKU, or barcode returns matches.
F2.5 SKU and barcode uniqueness is enforced at the DB level and reported clearly on violation.

### F3 Stock
F3.1 stock_movements ledger has product, delta, reason, reference, user, timestamp.
F3.2 product.stock is a cached value equal to sum of ledger deltas (invariant test).
F3.3 stock can never go negative (test).
F3.4 concurrent decrement on Postgres with at least 20 parallel attempts on stock of 5 never goes negative.
F3.5 low-stock list returns products at or below their threshold.
F3.6 receive-stock form adds a positive ledger entry.
F3.7 adjustments require a reason and record the reason on the ledger.

### F4 POS and sales
F4.1 cart supports add by barcode (USB scanner types digits + Enter), search, quantity edit, discount (fixed or percent), and three payment methods (cash, mobile wallet, due).
F4.2 discount is capped at the subtotal; percent rounding is exact (integer math, tested including 0, 100%, over-cap, odd amounts).
F4.3 due sales require a customer (name + phone).
F4.4 sale number is YYYYMMDD-NNNN, per day, gap-free and unique under concurrency (test on Postgres).
F4.5 every sale line snapshots price at sale time; later price changes do not affect past sales.
F4.6 stock decrement is transactional; a sale that would make any line negative fails as a whole with no partial changes.
F4.7 void (owner only, with reason) restores stock exactly once; voiding twice is rejected.
F4.8 due payments can be recorded; outstanding balance list shows per-customer totals.

### F5 Invoices
F5.1 PDF per sale is generated via reportlab with shop name, address, phone, items, discount, total, paid, due.
F5.2 Bangla text renders correctly using the bundled Noto Sans Bengali font (test by extracting text and verifying font embedding).
F5.3 cashier and owner can reprint an invoice PDF by sale number.

### F6 Reports
F6.1 daily and monthly sales totals match the sum of sales in the SHOP_TIMEZONE day/month.
F6.2 payment-method breakdown sums to the daily/monthly total.
F6.3 top 10 products by quantity for the period.
F6.4 profit equals sum of (line sell price - line cost snapshot) * quantity, minus discounts.
F6.5 outstanding dues list per customer.
F6.6 CSV export neutralizes cells starting with = + - @ in text fields.
F6.7 only owner can open report pages; cashiers get 403.
F6.8 day/month boundary tests use frozen time in Asia/Dhaka (default).

### F7 Offline PWA
F7.1 manifest and icons are served; app is installable.
F7.2 service worker caches the app shell with a versioned cache; a new deployment updates the shell safely (update flow test).
F7.3 POS screen works offline from a cached product list.
F7.4 offline sales are stored in IndexedDB with a client-generated UUID idempotency key.
F7.5 POST /api/sales with the same idempotency key twice returns the same sale and creates one stock movement.
F7.6 UI shows a pending-sales badge while offline sales are unsynced.
F7.7 unit prices for offline-synced sales come from the client; any mismatch with the current product price is flagged for owner review.
F7.8 a sale that cannot be accepted at sync (e.g. insufficient stock) goes to a "needs review" list and is never silently dropped or duplicated.
F7.9 offline mode never exposes pages other than the POS shell and cached product list.

### F8 Operations
F8.1 GET /health returns 200 with a small JSON body.
F8.2 backup script works on Postgres (pg_dump) and SQLite (sqlite3 .backup).
F8.3 restore test: back up, wipe, restore, all counts and stock totals match.
F8.4 demo seed is idempotent (running twice creates no duplicates): grocery shop, 50 products, 3 customers.
F8.5 settings page: shop details, currency symbol, timezone, invoice footer.
F8.6 /health endpoint exists and returns 200; smoke test script exists and exits non-zero on failure.

### Global
G1 docker compose up --build serves the app; the seed command loads demo data; a fresh clone works from the README.
G2 Stock never goes negative, including under concurrent sales (Postgres test with threads).
G3 Money math is exact: discounts, percent rounding and totals are tested with integer arithmetic, including edge cases.
G4 Posting the same offline sale twice (same idempotency key) creates exactly one sale and one stock movement.
G5 Offline end-to-end test: go offline, make a sale, go online, the sale syncs once.
G6 Owner-only routes reject cashiers (parametrized over all routes); all state-changing routes enforce CSRF.
G7 A restore test proves a backup can be restored into an empty database.
G8 CI is green on Postgres.
