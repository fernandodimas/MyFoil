#!/usr/bin/env python3
"""
Backfill helper to precompute user_title_flags for a single user.

Usage:
  python3 scripts/backfill_user_title_flags_for_user.py --user-id 123 [--limit N]

This is a lightweight helper to run precompute for one user (useful for tests
or to update a single user's flags after changing ignore prefs).
"""

import sys
import time
import argparse
import os

# Ensure project root and app/ are importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

try:
    from app import app
    from repositories.titles_repository import TitlesRepository
    from repositories.user_repository import UserRepository
except Exception as e:
    print(
        "Failed to import application modules. Run this script from the project root or ensure PYTHONPATH contains the repo root."
    )
    raise


def main(user_id: int, limit: int):
    with app.app_context():
        user = UserRepository.get_by_id(user_id)
        if not user:
            print(f"User with id={user_id} not found")
            return 1

        print(f"Precomputing flags for user id={user_id} (limit={limit})")
        start = time.time()
        try:
            TitlesRepository.precompute_flags_for_user(user_id, limit=limit)
        except Exception as e:
            print(f"Error during precompute: {e}")
            return 2
        duration = time.time() - start
        print(f"Done in {duration:.2f}s")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=int, required=True, help="User id to process")
    parser.add_argument("--limit", type=int, default=1000, help="How many titles to process for this user")
    args = parser.parse_args()
    exit(main(args.user_id, args.limit))
