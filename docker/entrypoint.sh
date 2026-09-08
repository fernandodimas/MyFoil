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
  # - timeout 60: reduced from 120s - if request takes longer, something is wrong
  # - worker-class gevent: async workers for I/O bound operations
  # - workers: default to 2, override with GUNICORN_WORKERS env
  # - max-requests: recycle workers more aggressively to prevent memory leaks
  # - preload: load app once per worker to share memory
  exec gunicorn -k gevent \
    -b 0.0.0.0:8465 \
    --chdir /app \
    --timeout 60 \
    --workers ${GUNICORN_WORKERS:-2} \
    --max-requests 500 \
    --max-requests-jitter 50 \
    --worker-tmp-dir /dev/shm \
    --preload \
    "${TARGET}:create_app()"
fi
