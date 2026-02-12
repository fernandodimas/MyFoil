#!/usr/bin/env python3
"""
Post-deploy recompute script

Intended to run once after a new Docker image is deployed. Steps:
 - Apply title counter columns/indexes (idempotent)
 - Run update_titles() under advisory lock
 - Regenerate library cache (force)

This script is safe to run multiple times and will bail out if another process
holds the advisory lock.
"""

import subprocess
import sys
import time
from db import db


def acquire_lock(conn, lock_id: int) -> bool:
    try:
        res = conn.execute(db.text(f"SELECT pg_try_advisory_lock({lock_id});")).scalar()
        return bool(res)
    except Exception:
        return False


def release_lock(conn, lock_id: int):
    try:
        conn.execute(db.text(f"SELECT pg_advisory_unlock({lock_id});"))
    except Exception:
        pass


def run_cmd(cmd):
    print(f">> Running: {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        print(proc.stdout)
        return proc.returncode == 0
    except Exception as e:
        print(f"Command failed: {e}")
        return False


def main():
    # Use separate connection for advisory lock
    app = None
    try:
        # Import create_app lazily to avoid side effects at import time
        from app.app import create_app

        app = create_app()
    except Exception as e:
        print("Failed to import application factory:", e)
        sys.exit(2)

    with app.app_context():
        conn = db.engine.connect()
        LOCK_ID = 999999999
        print("Attempting to acquire advisory lock for post-deploy recompute...")
        if not acquire_lock(conn, LOCK_ID):
            print("Could not acquire advisory lock; another process is running. Exiting.")
            conn.close()
            return

        try:
            # 1) Apply title counters (idempotent)
            print("Applying title counters (ALTER TABLE / indices)")
            run_cmd(["python3", "/app/scripts/apply_title_counters.py"])

            # 2) Run update_titles (safe wrapper with its own advisory lock)
            print("Running update_titles (may take time)")
            run_cmd(["python3", "/app/scripts/run_update_titles.py"])

            # 3) Regenerate library cache (force)
            print("Regenerating library cache (force=True)")
            try:
                import library

                library.invalidate_library_cache()
                # Force regenerate in current process (will load TitleDB)
                library.generate_library(force=True)
                print("Library regeneration completed.")
            except Exception as e:
                print("Library regeneration failed:", e)

            print("Post-deploy recompute finished successfully.")

        except Exception as e:
            print("Error during post-deploy recompute:", e)
        finally:
            release_lock(conn, LOCK_ID)
            conn.close()


if __name__ == "__main__":
    main()
