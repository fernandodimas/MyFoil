#!/usr/bin/env bash
set -euo pipefail
# Default entrypoint for container. It will run migrations by default and then start
# the app unless DISABLE_AUTO_MIGRATE=1 is set. Auto-migrate is conservative and
# only runs alembic upgrade head; it will not run the heavy backfill automatically.

# Execute passed command or start default gunicorn
if [[ $# -gt 0 ]]; then
  exec "$@"
else
  # Decide gunicorn app target depending on package layout inside the container.
  TARGET=$(python3 - <<'PY' | tail -n1
import importlib, sys, contextlib, io
_devnull = open('/dev/null', 'w')
for candidate in ("app.app", "app"):
    try:
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
  # Gunicorn settings:
  # - timeout 180: allow time for TitleDB and disk operations
  # - worker-class eventlet: async workers for SocketIO long-polling support
  # - workers: single worker to minimize memory (override with GUNICORN_WORKERS)
  # - max-requests: recycle workers periodically without thrashing on every page load
  exec gunicorn \
    -b 0.0.0.0:8465 \
    --chdir /app \
    --timeout ${GUNICORN_TIMEOUT:-180} \
    --workers ${GUNICORN_WORKERS:-1} \
    --worker-class eventlet \
    --max-requests ${GUNICORN_MAX_REQUESTS:-2000} \
    --max-requests-jitter ${GUNICORN_MAX_REQUESTS_JITTER:-200} \
    --worker-tmp-dir /dev/shm \
    "${TARGET}:create_app()"
fi
