PROJECT: ShopDesk
PURPOSE: Inventory, billing and daily sales reports for a small shop. Usable on a cheap laptop or phone, and the POS keeps working when the internet drops.

IN SCOPE
F1 Auth and roles: owner and cashier. Owner-only: cost prices, profit, reports, users, stock adjustments, voids, settings. Cashier: POS, view products and stock, reprint invoices. argon2 passwords, signed session cookies, CSRF on all state-changing requests, login rate limit, owner created by CLI or from env on first start, password change.
F2 Catalog: categories; products (name, SKU unique, barcode unique and optional, unit, sell price, cost price, low-stock threshold, active flag). ALL money is stored as integer minor units (paisa), never floats. CSV import of products with a dry run and a row-level error report. Search by name, SKU or barcode.
F3 Stock: a stock_movements ledger (product, delta, reason: opening/purchase/sale/void/adjustment, reference, user, timestamp); product.stock is a cached value updated in the SAME transaction; stock can never go negative; low-stock list; "receive stock" form; adjustments require a reason.
F4 POS and sales: cart; barcode input field that works with USB scanners (they type digits + Enter); search; quantity editing; discount (fixed amount or percent, capped at the subtotal); payment method (cash, mobile wallet, due); customer (name + phone, required for due sales); sale number YYYYMMDD-NNNN, per day, gap-free and unique under concurrency; price snapshot on every line; transactional stock decrement; void sale (owner only, with reason, restores stock); record due payments and list customers with outstanding balances.
F5 Invoices: PDF per sale (reportlab) with shop name, address, phone, items, discount, total, paid and due; Bangla text must render correctly using a bundled OFL-licensed Noto Sans Bengali font (license file kept).
F6 Reports (owner only): daily and monthly sales totals, payment-method breakdown, top 10 products, profit (sell minus cost snapshot), outstanding dues; CSV export; day and month boundaries in SHOP_TIMEZONE (default Asia/Dhaka).
F7 Offline POS (PWA): installable (manifest and icons); service worker caches the app shell with a versioned cache and a safe update flow; the POS screen works offline from a cached product list; sales made offline are stored in IndexedDB with a client-generated UUID idempotency key and synced when the connection returns; POST /api/sales is idempotent (same key twice returns the original sale); the UI shows a pending-sales badge; unit prices for offline-synced sales come from the client (the customer was already charged) and any mismatch with the current price is flagged for owner review; a sale that cannot be accepted at sync (for example insufficient stock) goes to a "needs review" list and is never silently dropped and never duplicated.
F8 Operations: GET /health; backup script (pg_dump for Postgres, sqlite3 .backup for SQLite) with scripts/restore.sh and a restore test; idempotent demo seed (grocery shop, 50 products, 3 customers); settings page (shop details, currency symbol, timezone, invoice footer).

OUT OF SCOPE
Multi-shop, suppliers and purchase orders, returns other than void, taxes/VAT, camera-based barcode scanning, payment gateway integration, receipt-printer drivers, accounting, SMS, translations of the UI, desktop app, anything not listed above.

ALLOWED STACK
Python 3.12; FastAPI; uvicorn; SQLModel; Alembic; psycopg[binary]; pydantic-settings; Jinja2; python-multipart; argon2-cffi; reportlab; vendored HTMX (eval disabled); vanilla JavaScript (ES modules) with IndexedDB and a service worker; bundled Noto Sans Bengali font file; pytest, pytest-playwright, httpx, freezegun; ruff; Docker; GitHub Actions.

GLOBAL ACCEPTANCE CRITERIA
G1 docker compose up --build serves the app; the seed command loads demo data; a fresh clone works from the README.
G2 Stock never goes negative, including under concurrent sales (Postgres test with threads).
G3 Money math is exact: discounts, percent rounding and totals are tested with integer arithmetic, including edge cases.
G4 Posting the same offline sale twice (same idempotency key) creates exactly one sale and one stock movement.
G5 Offline end-to-end test: go offline, make a sale, go online, the sale syncs once.
G6 Owner-only routes reject cashiers (parametrized over all routes); all state-changing routes enforce CSRF.
G7 A restore test proves a backup can be restored into an empty database.
G8 CI is green on Postgres.

MILESTONES
M1 Foundation; M2 Auth and roles; M3 Catalog and stock; M4 Sales and POS; M5 Invoices and reports; M6 Offline PWA; M7 Backups, seed, settings, end-to-end tests.
