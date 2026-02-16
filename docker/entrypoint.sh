#!/usr/bin/env bash
set -euo pipefail
# Default entrypoint for container. It will run migrations by default and then start
# the app unless DISABLE_AUTO_MIGRATE=1 is set. Auto-migrate is conservative and
# only runs alembic upgrade head; it will not run the heavy backfill automatically.

if [[ "${DISABLE_AUTO_MIGRATE:-0}" != "1" ]]; then
  if [[ -n "${DATABASE_URL:-}" ]]; then
    echo "[entrypoint] Running alembic upgrade head"
    # Prefer running migrations via the in-app helper which runs flask-migrate
    # under the application context to avoid "Working outside of application context"
    MIGRATE_HELPER="/app/scripts/docker/run_migrations_under_app.py"
    if [[ -f "$MIGRATE_HELPER" ]]; then
      echo "[entrypoint] Running migrations via $MIGRATE_HELPER"
      python3 "$MIGRATE_HELPER" || {
        echo "[entrypoint] migration helper failed; falling back to alembic CLI"
      }
    fi
    # Fallback: try alembic CLI if present (some deployments prefer it)
    ALEMBIC_CONF="/app/migrations/alembic.ini"
    if command -v alembic >/dev/null 2>&1 && [[ -f "$ALEMBIC_CONF" ]]; then
      echo "[entrypoint] Running alembic CLI as fallback"
      python3 -m alembic -c "$ALEMBIC_CONF" upgrade head || {
        echo "[entrypoint] Alembic CLI upgrade failed; continuing startup"
      }
    else
      echo "[entrypoint] Alembic CLI not available or config missing; skipping CLI step"
    fi
  else
    echo "[entrypoint] DATABASE_URL not set; skipping alembic"
  fi
fi

# Execute passed command or start default gunicorn
if [[ $# -gt 0 ]]; then
  exec "$@"
else
  # Decide gunicorn app target depending on package layout inside the container.
  # If the repository was copied so that /app is the package root, importing
  # "app.app" may fail because 'app' is a module. Try to detect the correct
  # module to pass to gunicorn.
  TARGET=$(python3 - <<'PY' | tail -n1
import importlib, sys, contextlib, io
_devnull = open('/dev/null', 'w')
for candidate in ("app.app", "app"):
    try:
        # suppress stdout/stderr during import to avoid capturing module prints
        with contextlib.redirect_stdout(_devnull), contextlib.redirect_stderr(_devnull):
            importlib.import_module(candidate)
        print(candidate)
        sys.exit(0)
    except Exception:
        pass
print("app")
_devnull.close()
PY
)
  echo "[entrypoint] Using gunicorn target: ${TARGET}:create_app()"
  exec gunicorn -b 0.0.0.0:8465 --chdir /app "${TARGET}:create_app()"
fi
