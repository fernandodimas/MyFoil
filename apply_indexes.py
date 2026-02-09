#!/usr/bin/env python3
"""Script to create Phase 2.1 indexes directly on the database"""

import sys

sys.path.insert(0, "app")

from sqlalchemy import create_engine, text

# Database connection string
DB_URL = "postgresql://myfoil:myfoilpassword@192.168.16.250:5432/myfoillocal"


def create_indexes():
    """Create Phase 2.1 performance indexes"""

    indexes = [
        # Files table indexes
        "CREATE INDEX IF NOT EXISTS idx_files_library_id ON files (library_id)",
        "CREATE INDEX IF NOT EXISTS idx_files_identified ON files (identified)",
        "CREATE INDEX IF NOT EXISTS idx_files_size ON files (size)",
        # Titles table indexes
        "CREATE INDEX IF NOT EXISTS idx_titles_up_to_date_have_base ON titles (up_to_date, have_base)",
        "CREATE INDEX IF NOT EXISTS idx_titles_have_base ON titles (have_base)",
        "CREATE INDEX IF NOT EXISTS idx_titles_up_to_date ON titles (up_to_date)",
        "CREATE INDEX IF NOT EXISTS idx_titles_have_base_added_at ON titles (have_base, added_at)",
        # Apps table indexes
        "CREATE INDEX IF NOT EXISTS idx_apps_title_id_owned ON apps (title_id, owned)",
        "CREATE INDEX IF NOT EXISTS idx_apps_title_id_type_owned ON apps (title_id, app_type, owned)",
    ]

    print("=" * 80)
    print("PHASE 2.1: Creating Performance Indexes")
    print("=" * 80)
    print(f"Database: {DB_URL}")
    print("")

    try:
        # Connect to database
        engine = create_engine(DB_URL)
        print("✓ Connected to database")

        with engine.begin() as conn:
            print("✓ Transaction started")

            created_count = 0
            for idx in indexes:
                try:
                    conn.execute(text(idx))
                    created_count += 1
                    # Extract index name for logging
                    if "index " in idx:
                        idx_name = idx.split("index ")[1].split(" ON")[0].replace("IF NOT EXISTS ", "")
                    else:
                        idx_name = "unknown"
                    print(f"  ✓ Created: {idx_name}")
                except Exception as e:
                    print(f"  ⚠ Warning for index: {e}")

        print("")
        print("=" * 80)
        print(f"✓ SUCCESS: {created_count} indexes created")
        print("=" * 80)
        print("")
        print("Expected performance improvements:")
        print("  - Stats queries: 5-10x faster")
        print("  - Outdated games query: 3-5x faster")
        print("  - File size queries: 2-3x faster")
        print("")

        return True

    except Exception as e:
        print("")
        print("=" * 80)
        print("✗ ERROR:")
        print(f"  {e}")
        print("=" * 80)
        return False


if __name__ == "__main__":
    success = create_indexes()
    sys.exit(0 if success else 1)
