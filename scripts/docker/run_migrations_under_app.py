"""
Run Alembic/Flask-Migrate upgrade under the Flask application context.

This avoids the "Working outside of application context" error when env.py
tries to access current_app.extensions['migrate'].

Usage: python3 /app/scripts/docker/run_migrations_under_app.py
"""

import sys
import logging
import os

# Ensure the application directory is on sys.path when running inside a container
# The container layout places the code at /app; add it so imports like `import app`
# succeed even when the current working dir is different.
APP_ROOT = os.environ.get("APP_ROOT", "/app")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

try:
    # Try common import locations for the application factory
    from importlib import import_module

    try:
        app_mod = import_module("app")
    except Exception:
        # Fallback to app.app if package layout differs
        app_mod = import_module("app.app")

    create_app = getattr(app_mod, "create_app", None)
    if create_app is None:
        raise ImportError("Could not find create_app in app package/module")

    from flask_migrate import upgrade
except Exception as e:
    print("Failed to import application or flask_migrate:", e, file=sys.stderr)
    raise


def main():
    app = create_app()
    # Ensure logging is initialized
    logging.getLogger().setLevel(logging.INFO)
    with app.app_context():
        print("[run_migrations_under_app] Migrations are disabled by user request. Skipping upgrade.")
        return


if __name__ == "__main__":
    main()
