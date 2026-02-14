#!/usr/bin/env bash
set -euo pipefail
# Simple migration + backfill helper intended to run inside the app Docker image
# Usage (container):
#   DATABASE_URL="postgresql://..." /usr/local/bin/migrate_and_backfill.sh --batch-size 100
# Environment variables:
#   DATABASE_URL (required) - Postgres connection string
#   BACKUP_DIR (optional, default /data/backups)
#   BATCH_SIZE (optional, default 100)
#   DRY_RUN=1 (optional) - do everything except run the backfill upserts

BACKUP_DIR=${BACKUP_DIR:-/data/backups}
BATCH_SIZE=${BATCH_SIZE:-100}
DRY_RUN=${DRY_RUN:-0}

usage() {
  cat <<EOF
Usage: migrate_and_backfill.sh [--batch-size N]
Runs pg_dump backup, alembic upgrade, and the backfill script inside the container.
Requires: DATABASE_URL env var set and the container must include pg_dump, alembic and python3.
Environment variables:
  DATABASE_URL - Postgres connection string (required)
  BACKUP_DIR - where to store pg_dump (default: $BACKUP_DIR)
  BATCH_SIZE - titles per user to process (default: $BATCH_SIZE)
  DRY_RUN=1 - don't run the final backfill upserts
EOF
}

# parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --batch-size)
      BATCH_SIZE="$2"; shift 2;;
    -h|--help)
      usage; exit 0;;
    *)
      echo "Unknown arg: $1"; usage; exit 2;;
  esac
done

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL must be set" >&2
  usage
  exit 3
fi

mkdir -p "$BACKUP_DIR"
TS=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_FILE="$BACKUP_DIR/myfoil_preflags_${TS}.dump"

echo "[migrate_and_backfill] Starting backup to $BACKUP_FILE"
if command -v pg_dump >/dev/null 2>&1; then
  pg_dump --dbname="$DATABASE_URL" -Fc -f "$BACKUP_FILE"
  echo "[migrate_and_backfill] Backup finished"
else
  echo "[migrate_and_backfill] Warning: pg_dump not found in container; skipping backup" >&2
fi

echo "[migrate_and_backfill] Applying alembic migrations"
python3 -m alembic -c app/migrations/alembic.ini upgrade head
echo "[migrate_and_backfill] Alembic finished"

if [[ "$DRY_RUN" == "1" ]]; then
  echo "[migrate_and_backfill] DRY_RUN=1 set, skipping backfill step"
  exit 0
fi

echo "[migrate_and_backfill] Running backfill with batch-size=$BATCH_SIZE"
python3 scripts/backfill_user_title_flags.py --batch-size "$BATCH_SIZE"
echo "[migrate_and_backfill] Backfill finished"

exit 0
