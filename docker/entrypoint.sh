#!/usr/bin/env bash
set -euo pipefail
# Default entrypoint for container. It will run migrations by default and then start
# the app unless DISABLE_AUTO_MIGRATE=1 is set. Auto-migrate is conservative and
# only runs alembic upgrade head; it will not run the heavy backfill automatically.

if [[ "${DISABLE_AUTO_MIGRATE:-0}" != "1" ]]; then
  if [[ -n "${DATABASE_URL:-}" ]]; then
    echo "[entrypoint] Running alembic upgrade head"
    # Use absolute path to alembic.ini to avoid relative-path issues in some runtimes
    ALEMBIC_CONF="/app/migrations/alembic.ini"
    if [[ -f "$ALEMBIC_CONF" ]]; then
      python3 -m alembic -c "$ALEMBIC_CONF" upgrade head || {
        echo "[entrypoint] Alembic upgrade failed; continuing startup"
      }
    else
      echo "[entrypoint] Alembic config not found at $ALEMBIC_CONF; skipping"
    fi
  else
    echo "[entrypoint] DATABASE_URL not set; skipping alembic"
  fi
fi

# Execute passed command or start default gunicorn
if [[ $# -gt 0 ]]; then
  exec "$@"
else
  exec gunicorn -b 0.0.0.0:8465 --chdir /app "app.app:create_app()"
fi
