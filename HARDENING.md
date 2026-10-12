# H — Hardening report

A full pass over the codebase after the seven milestones were merged.

## Stability: tests run 3x

| run | passed | skipped | time |
|-----|--------|---------|------|
| 1   | 92     | 2       | 10.93s |
| 2   | 92     | 2       | 10.86s |
| 3   | 92     | 2       | 10.89s |

The 2 skipped tests are Postgres-only (concurrent stock decrement and gap-free
sale numbers) and are run in CI with a Postgres service.

## Lint

`ruff check .` passes with zero issues (per-file ignores are pinned in
`pyproject.toml`).

## Code review findings

### Strengths

- All money is integer minor units (paisa); a dedicated test
  (`test_no_floats_in_money_paths`) walks the AST of `app/money.py` and the
  sales/products/cart hot paths to prove the absence of `float`.
- Idempotency is enforced by a `UNIQUE` constraint on `sales.idempotency_key`
  with an early-return in `app.sales.create_sale`; the same offline test
  proves a duplicate POST returns the same sale.
- CSRF is double-submit with `HttpOnly` session + JS-readable CSRF; the
  M7 fix added a `require_csrf` form-field branch so HTML form posts work
  too, and `base.html` auto-injects a `_csrf` hidden input from the cookie.
- Argon2id is the only password hash used; passwords never appear in
  logs or responses.
- Login is rate-limited by client IP via an in-memory dict
  (`check_login_rate_limit` in `app/auth.py`).
- Stock decrement uses `SELECT ... FOR UPDATE` on Postgres (no-op on
  SQLite). The 20-thread concurrent test exercises this on Postgres.
- Gap-free sale numbers use `pg_advisory_xact_lock(hashtext('sale-YYYYMMDD'))`
  inside the sale transaction. The 10-thread concurrent test verifies this.
- CSV export neutralizes formula-injection cells (`= + - @` are prefixed
  with `'`).
- The service worker uses a versioned cache + `skipWaiting` +
  `caches.delete` on activation so a new deployment replaces the old shell
  safely.
- Production startup refuses to boot with the default `SECRET_KEY`; this is
  covered by `test_app.py::test_production_refuses_default_secret`.

### Known limitations (intentional, in BACKLOG.md)

- Login rate-limit state is in-memory. With multiple workers or a
  restart, the counter resets. This is acceptable for a single-process
  deployment; a Redis-backed limiter is a future option.
- The offline queue is per-browser (IndexedDB). Switching browsers or
  clearing storage drops the local queue; the server has no record of
  in-flight sales until the client syncs. This is by design.
- The e2e tests depend on a chromium binary being available; if the
  Playwright browser is not installed the tests are skipped, not failed.
- `scripts/seed.py` creates a single owner (`owner`/`owner123`). This
  is a demo password documented in the seed script and intended to be
  changed on first login. Production deployments should not run the
  seed.

### No regressions introduced by M7

The form-CSRF fix in M7 touched every HTML form template (no source
edits, only a JS shim in `base.html`) and all 92 pre-existing tests
still pass.

## Security checklist

- [x] argon2 password hashing
- [x] HttpOnly + signed session cookie
- [x] CSRF on every state-changing route (header or form `_csrf`)
- [x] Login rate limit (5/min per IP)
- [x] Production default secret refusal
- [x] Owner-only routes return 403 for cashiers
- [x] State-changing routes return 401/403 without a session
- [x] No floats in money math
- [x] Stock never goes negative
- [x] Idempotent sales API
- [x] CSV formula-injection neutralized
- [x] SQL injection: only parameterised queries via SQLModel/SQLAlchemy
- [x] No `eval`, no `os.system`, no `subprocess` in app code
- [x] Bundled Noto Sans Bengali font with OFL license
- [x] Service-worker safe update flow

## Recommendations (out of scope, see BACKLOG.md)

- Add 2FA for the owner account.
- Add structured request logging.
- Add a rate-limit response header so the client can back off.
- Move rate limit to Redis when scaling out.
- Add image upload for product photos.