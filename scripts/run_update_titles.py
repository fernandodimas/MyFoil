#!/usr/bin/env python3
"""
Run update_titles() safely under the Flask app context with advisory lock and logging.
"""

import sys
import time
from db import db

try:
    from app.app import create_app
    from library import update_titles
except Exception as e:
    print("Failed to import application or update_titles:", e)
    sys.exit(2)


def main():
    app = create_app()
    with app.app_context():
        conn = db.engine.connect()
        try:
            LOCK_ID = 123456789
            print("Trying to acquire advisory lock for update_titles...")
            res = conn.execute(db.text(f"SELECT pg_try_advisory_lock({LOCK_ID});")).scalar()
            if not res:
                print("Could not acquire lock, another process is running. Exiting.")
                return
            print("Lock acquired, running update_titles...")
            start = time.time()
            update_titles()
            duration = time.time() - start
            print(f"update_titles finished in {duration:.2f}s")
        except Exception as e:
            print("Error while running update_titles:", e)
        finally:
            try:
                conn.execute(db.text(f"SELECT pg_advisory_unlock({LOCK_ID});"))
            except Exception:
                pass
            conn.close()


if __name__ == "__main__":
    main()
