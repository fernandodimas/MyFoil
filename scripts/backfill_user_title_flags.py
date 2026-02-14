#!/usr/bin/env python3
"""
Backfill script to precompute user_title_flags for all users.

Usage:
  scripts/backfill_user_title_flags.py [--batch-size N]

This will iterate users and compute flags for recent titles in batches.
It uses TitlesRepository.precompute_flags_for_user which performs upserts
via services.user_title_flags_service. Run this from the project root where
the Flask app can be imported (or adapt FLASK_APP as needed).
"""

import sys
import time
import argparse
import os

# Ensure project root is on sys.path so `app` package can be imported when
# the script is executed directly from the repository root or from CI.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# Also ensure `app` package modules that import `constants` as a top-level module
# can find `constants.py` by adding the app/ directory to sys.path as well.
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

try:
    from app import app  # ensures app context / db initialization
    from repositories.user_repository import UserRepository
    from repositories.titles_repository import TitlesRepository
except Exception as e:
    print(
        "Failed to import application modules. Run this script from the project root or ensure PYTHONPATH contains the repo root."
    )
    raise


def main(batch_size: int):
    with app.app_context():
        users = UserRepository.get_all()
        total = len(users)
        print(f"Found {total} users; processing with batch size={batch_size}")

        idx = 0
        for u in users:
            idx += 1
            print(f"[{idx}/{total}] Precomputing flags for user id={u.id}")
            try:
                TitlesRepository.precompute_flags_for_user(u.id, limit=batch_size)
            except Exception as e:
                print(f"  Error computing for user {u.id}: {e}")
            # small pause to avoid DB overload
            time.sleep(0.05)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=1000, help="How many titles to process per user")
    args = parser.parse_args()
    main(args.batch_size)
