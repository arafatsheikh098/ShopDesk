#!/usr/bin/env bash
# smoke_test.sh — exit 0 on healthy service, non-zero on failure.
#
# Usage:
#   BASE=http://127.0.0.1:8000 ./scripts/smoke_test.sh
#
# Checks:
#   1. /health returns 200 and a JSON body with status=ok
#   2. The static manifest is served
#   3. The login page renders (200)
#   4. POST /api/auth/login with bad creds returns 401
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8000}"

red() { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
fail() { red "FAIL: $*"; exit 1; }
ok() { green "ok: $*"; }

# 1) /health
code=$(curl -fsS -o /tmp/shopdesk_health.json -w "%{http_code}" "$BASE/health") \
  || fail "GET /health failed"
[ "$code" = "200" ] || fail "GET /health returned $code"
grep -q '"status":"ok"' /tmp/shopdesk_health.json \
  || fail "/health body missing status:ok"
ok "/health -> 200"

# 2) manifest
code=$(curl -fsS -o /tmp/shopdesk_manifest.json -w "%{http_code}" "$BASE/static/manifest.webmanifest") \
  || fail "GET manifest failed"
[ "$code" = "200" ] || fail "GET manifest returned $code"
grep -q "ShopDesk" /tmp/shopdesk_manifest.json \
  || fail "manifest missing ShopDesk name"
ok "/static/manifest.webmanifest -> 200"

# 3) login page renders
code=$(curl -fsS -o /dev/null -w "%{http_code}" "$BASE/login") \
  || fail "GET /login failed"
[ "$code" = "200" ] || fail "GET /login returned $code"
ok "/login -> 200"

# 4) bad creds -> 401
code=$(curl -sS -o /tmp/shopdesk_login.json -w "%{http_code}" \
  -H "Content-Type: application/json" \
  --data '{"username":"nope","password":"nope"}' \
  "$BASE/api/auth/login") || true
[ "$code" = "401" ] || [ "$code" = "429" ] \
  || fail "bad login -> $code (expected 401 or 429)"
ok "bad login -> $code"

# 5) service worker
code=$(curl -fsS -o /tmp/shopdesk_sw.js -w "%{http_code}" "$BASE/static/sw.js") \
  || fail "GET sw.js failed"
[ "$code" = "200" ] || fail "GET sw.js returned $code"
grep -q "service" /tmp/shopdesk_sw.js || fail "sw.js missing 'service'"
ok "/static/sw.js -> 200"

green "SMOKE TEST PASSED"
exit 0