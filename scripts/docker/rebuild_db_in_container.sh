#!/usr/bin/env bash
set -euo pipefail
# Rebuild DB script intended to run INSIDE the app container (one-off)
# It assumes the application's code is at /app and that the container has
# postgresql client (pg_dump), python3 and the project scripts available.
#
# Usage (container):
#   export DATABASE_URL='postgresql://user:pass@host:5432/db'
#   export BACKUP_DIR=/data/backups
#   export BATCH_SIZE=100
#   export DRY_RUN=0    # set 1 to skip backfill writes
#   /app/scripts/docker/rebuild_db_in_container.sh

BACKUP_DIR=${BACKUP_DIR:-/data/backups}
BATCH_SIZE=${BATCH_SIZE:-100}
DRY_RUN=${DRY_RUN:-0}

echo "Rebuild script started"
if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL not set. Export it before running." >&2
  exit 2
fi

mkdir -p "$BACKUP_DIR"
TS=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_FILE="$BACKUP_DIR/myfoil_pre_recreate_${TS}.dump"

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "ERROR: pg_dump not found in container. Install postgresql-client in the image." >&2
  exit 3
fi

echo "1/6 - Running pg_dump to $BACKUP_FILE"
pg_dump --dbname="$DATABASE_URL" -Fc -f "$BACKUP_FILE"
echo "Backup completed"

echo "2/6 - Dropping and recreating public schema via application context"
python3 - <<'PY'
from importlib import import_module
try:
    try:
        app_mod = import_module('app')
    except Exception:
        app_mod = import_module('app.app')
    create_app = getattr(app_mod, 'create_app', None)
    if create_app is None:
        raise RuntimeError('create_app not found')
    app = create_app()
    from db import db
    with app.app_context():
        conn = db.engine.connect()
        conn = conn.execution_options(isolation_level='AUTOCOMMIT')
        print('Executing DROP SCHEMA public CASCADE; CREATE SCHEMA public;')
        conn.execute('DROP SCHEMA public CASCADE')
        conn.execute('CREATE SCHEMA public')
        conn.close()
    print('Schema recreated')
except Exception as e:
    print('Error during schema recreate:', e)
    raise
PY

echo "3/6 - Applying migrations under app context"
if [[ -f "/app/scripts/docker/run_migrations_under_app.py" ]]; then
  python3 /app/scripts/docker/run_migrations_under_app.py
else
  if command -v alembic >/dev/null 2>&1 && [[ -f "/app/migrations/alembic.ini" ]]; then
    python3 -m alembic -c /app/migrations/alembic.ini upgrade head
  else
    echo "WARNING: migrations helper and alembic CLI not available; ensure migrations are applied manually" >&2
  fi
fi

echo "4/6 - Rebuilding Titles/Apps (update_titles)"
if [[ -f "/app/scripts/run_update_titles.py" ]]; then
  python3 /app/scripts/run_update_titles.py
else
  echo "WARNING: run_update_titles.py not found; run update_titles() manually if needed" >&2
fi

echo "5/6 - Backfill user_title_flags (batch-size=$BATCH_SIZE). DRY_RUN=$DRY_RUN"
if [[ "$DRY_RUN" == "1" ]]; then
  echo "DRY_RUN=1 -> skipping backfill writes";
else
  if [[ -f "/usr/local/bin/migrate_and_backfill.sh" ]]; then
    /usr/local/bin/migrate_and_backfill.sh --batch-size "$BATCH_SIZE"
  elif [[ -f "/app/scripts/backfill_user_title_flags.py" ]]; then
    python3 /app/scripts/backfill_user_title_flags.py --batch-size "$BATCH_SIZE"
  else
    echo "WARNING: backfill script not found; skipping backfill" >&2
  fi
fi

echo "6/6 - Rebuild finished. Backup kept at: $BACKUP_FILE"
echo "Please restart your app container (if not handled by orchestration) and verify logs/UI"

exit 0
