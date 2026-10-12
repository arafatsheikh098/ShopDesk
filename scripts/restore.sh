#!/usr/bin/env bash
# restore.sh — restore a ShopDesk backup produced by backup.sh.
#
# Usage:
#   ./scripts/restore.sh /path/to/backup.db.gz
#
# Detects the file type by name (shopdesk-pg-*.sql.gz vs shopdesk-sqlite-*.db.gz).
# SQLite: replaces the file in place (using .backup for safety).
# Postgres: pipes through psql.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCHIVE="${1:-}"
if [[ -z "$ARCHIVE" || ! -f "$ARCHIVE" ]]; then
  echo "usage: $0 /path/to/backup.gz" >&2
  exit 1
fi
DB_URL="${DATABASE_URL:-sqlite:///./shopdesk.db}"
BASE="$(basename "$ARCHIVE")"

if [[ "$BASE" == *sqlite* ]]; then
  case "$DB_URL" in
    sqlite:////*)
      DB_PATH="${DB_URL#sqlite:///}"
      ;;
    sqlite:///*)
      REL="${DB_URL#sqlite:///}"
      DB_PATH="$(cd "$HERE/.." && pwd)/$REL"
      ;;
    *)
      echo "unsupported sqlite URL: $DB_URL" >&2
      exit 3
      ;;
  esac
  mkdir -p "$(dirname "$DB_PATH")"
  TMP="$(mktemp -t shopdesk-restore-XXXXXX.db)"
  gunzip -c "$ARCHIVE" > "$TMP"
  sqlite3 "$TMP" ".backup '$DB_PATH'"
  rm -f "$TMP"
  echo "restored to $DB_PATH"
elif [[ "$BASE" == *pg* ]]; then
  if ! command -v psql >/dev/null 2>&1; then
    echo "psql not installed" >&2
    exit 2
  fi
  gunzip -c "$ARCHIVE" | psql "$DB_URL"
  echo "restored from $ARCHIVE"
else
  echo "unknown archive type: $BASE" >&2
  exit 3
fi