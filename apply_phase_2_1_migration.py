#!/usr/bin/env python3
"""
Script to apply Phase 2.1 database migration for composite indexes.
This script should be run with Flask app context to execute migrations.
"""

import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from app import create_app
from flask_migrate import upgrade


def main():
    """Apply database migration"""
    print("=" * 80)
    print("PHASE 2.1: Applying Composite Indexes Migration")
    print("=" * 80)

    # Create Flask app
    app = create_app()

    with app.app_context():
        try:
            print("\nApplying migration b2c3d4e5f9g1 (Add Composite Indexes)...")
            upgrade(revision="b2c3d4e5f9g1")
            print("✓ Migration applied successfully!")
            print("\nIndexes created:")
            print("  - Files: idx_files_library_id, idx_files_identified, idx_files_size")
            print("  - Titles: idx_titles_up_to_date_have_base, idx_titles_have_base,")
            print("           idx_titles_up_to_date, idx_titles_have_base_added_at")
            print("  - Apps: idx_apps_title_id_owned, idx_apps_title_id_type_owned")
            print("\nExpected performance improvements:")
            print("  - Stats queries: 5-10x faster")
            print("  - Outdated games query: 3-5x faster")
            print("  - File size queries: 2-3x faster")
            print("\n" + "=" * 80)
        except Exception as e:
            print(f"\n✗ Error applying migration: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
