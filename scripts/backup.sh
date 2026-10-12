#!/usr/bin/env bash
# backup.sh — back up the ShopDesk database.
#
# Usage:
#   ./scripts/backup.sh                 # writes backup to ./backups/
#   ./scripts/backup.sh /path/to/out    # writes backup to the given dir
#
# Detects SQLite vs Postgres from the DATABASE_URL env var (default
# sqlite:///./shopdesk.db). The output file is gzipped.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${1:-$HERE/../backups}"
mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DB_URL="${DATABASE_URL:-sqlite:///./shopdesk.db}"

if [[ "$DB_URL" == sqlite:* ]]; then
  # sqlite:///./shopdesk.db (3 slashes = relative) or sqlite:////abs/path (4 slashes = absolute)
  case "$DB_URL" in
    sqlite:////*)
      # Absolute path: strip sqlite:///, leaving the leading / on the path.
      DB_PATH="${DB_URL#sqlite:///}"
      ;;
    sqlite:///*)
      # Relative path: strip sqlite:///, then resolve from project root.
      REL="${DB_URL#sqlite:///}"
      DB_PATH="$(cd "$HERE/.." && pwd)/$REL"
      ;;
    *)
      echo "unsupported sqlite URL: $DB_URL" >&2
      exit 3
      ;;
  esac
  if [[ ! -f "$DB_PATH" ]]; then
    echo "no SQLite database at $DB_PATH" >&2
    exit 1
  fi
  OUT="$OUT_DIR/shopdesk-sqlite-$STAMP.db.gz"
  sqlite3 "$DB_PATH" ".backup '$OUT_DIR/.tmp-$STAMP.db'"
  gzip -c "$OUT_DIR/.tmp-$STAMP.db" > "$OUT"
  rm -f "$OUT_DIR/.tmp-$STAMP.db"
  echo "$OUT"
elif [[ "$DB_URL" == postgresql* || "$DB_URL" == postgres://* ]]; then
  if ! command -v pg_dump >/dev/null 2>&1; then
    echo "pg_dump not installed" >&2
    exit 2
  fi
  OUT="$OUT_DIR/shopdesk-pg-$STAMP.sql.gz"
  pg_dump "$DB_URL" | gzip > "$OUT"
  echo "$OUT"
else
  echo "unsupported DATABASE_URL: $DB_URL" >&2
  exit 3
fi