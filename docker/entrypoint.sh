#!/bin/bash
set -euo pipefail

# Ensure log dir exists
mkdir -p /var/log/myfoil
chown -R "${PUID:-1000}":"${PGID:-1000}" /var/log/myfoil || true

echo "MyFoil entrypoint starting..." | tee -a /var/log/myfoil/entrypoint.log

# Run database migrations if requested (default: enabled)
if [ "${RUN_MIGRATIONS_ON_START:-1}" = "1" ]; then
  echo "Running Alembic migrations..." | tee -a /var/log/myfoil/entrypoint.log
  if command -v alembic >/dev/null 2>&1; then
    alembic upgrade head 2>&1 | tee -a /var/log/myfoil/alembic.log || echo "alembic returned non-zero" | tee -a /var/log/myfoil/alembic.log
  else
    echo "alembic not found in PATH, skipping migrations" | tee -a /var/log/myfoil/entrypoint.log
  fi
fi

# Backfill materialized counters under advisory lock (disabled by default)
if [ "${RUN_BACKFILL_ON_START:-0}" = "1" ]; then
  echo "Attempting advisory lock for backfill..." | tee -a /var/log/myfoil/entrypoint.log
  DB_URL="${DATABASE_URL:-postgresql://myfoil:myfoilpassword@postgres:5432/myfoil}"
  LOCK_ID=987654321
  # Try to acquire lock
  LOCK_RES=$(psql "$DB_URL" -t -c "SELECT pg_try_advisory_lock($LOCK_ID);" 2>/dev/null || echo "f")
  LOCK_RES=$(echo "$LOCK_RES" | tr -d '[:space:]')
  if [ "$LOCK_RES" = "t" ] || [ "$LOCK_RES" = "true" ]; then
    echo "Advisory lock acquired, running backfill" | tee -a /var/log/myfoil/entrypoint.log
    python3 /app/scripts/apply_title_counters.py 2>&1 | tee -a /var/log/myfoil/backfill.log || true
    # Release lock
    psql "$DB_URL" -c "SELECT pg_advisory_unlock($LOCK_ID);" >/dev/null 2>&1 || true
  else
    echo "Could not acquire advisory lock; skipping backfill" | tee -a /var/log/myfoil/entrypoint.log
  fi
fi

# Optionally run update_titles (heavy) if explicitly enabled
if [ "${ENABLE_UPDATE_TITLES:-0}" = "1" ]; then
  echo "ENABLE_UPDATE_TITLES set, running update_titles (may be slow)" | tee -a /var/log/myfoil/entrypoint.log
  python3 /app/scripts/run_update_titles.py 2>&1 | tee -a /var/log/myfoil/update_titles.log || true
fi

# Post-deploy recompute hook: runs after image update when explicitly enabled
if [ "${RUN_POST_DEPLOY_RECOMPUTE:-0}" = "1" ]; then
  echo "RUN_POST_DEPLOY_RECOMPUTE set, running post-deploy recompute" | tee -a /var/log/myfoil/entrypoint.log
  python3 /app/scripts/post_deploy_recompute.py 2>&1 | tee -a /var/log/myfoil/post_deploy_recompute.log || true
fi

echo "Entrypoint finished setup, handing off to run.sh" | tee -a /var/log/myfoil/entrypoint.log

# Exec original run script (starts web or celery depending on args)
exec /app/run.sh "$@"
