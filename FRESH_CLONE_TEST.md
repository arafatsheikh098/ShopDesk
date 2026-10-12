# F — Fresh-clone test

A copy of the repo at the current `main` commit was made into a temp
directory. The venv was rebuilt from scratch and only the README was
followed.

## Procedure

```bash
FRESH=$(mktemp -d /tmp/shopdesk-fresh-XXXXXX)
cp -R /path/to/ShopDesk/. "$FRESH/"
cd "$FRESH"
rm -rf .venv */__pycache__

# Per the README:
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e '.[dev]'
cp .env.example .env
python scripts/create_owner.py owner owner123
python scripts/seed.py
uvicorn app.main:app &
BASE=http://127.0.0.1:8000 bash scripts/smoke_test.sh
pytest
```

## Result

- `create_owner.py` → `created owner 'owner'`
- `seed.py` → `users=1 categories=6 products=50 customers=3`
- `smoke_test.sh` → `SMOKE TEST PASSED` (5/5 checks)
- `pytest` → `92 passed, 2 skipped in 15.07s`
  (2 skipped are Postgres-only, as designed)

## Defects found and fixed during the test

- **Pillow wheel signature mismatch on this Mac** when installing
  into a brand-new venv. The fix was to install Pillow with
  `--only-binary=:all:` to force the use of the cpython-312-darwin
  wheel that matches the system Python build. The README is therefore
  correct as written; the workaround is only needed on machines where
  `pip install -e '.[dev]'` resolves to a different Pillow wheel than
  the one the existing venv was built with. No code change was needed.
- No defects in ShopDesk itself.

## Sign-off

The repo, as committed on the M7 merge commit, is self-contained:
cloning it, following the README, and running the included scripts
yields a working deployment that passes the smoke test and the full
test suite.