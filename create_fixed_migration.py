#!/usr/bin/env python3
"""Script to create a migration file that only creates indexes without modifying tables"""

import os

migration_content = '''"""Fix indexes for production without table modifications

This migration creates indexes directly on existing tables.
Use this for production databases that already have the schema but missing migration history.

Revision ID: b2c3d4e5fix
Revises: None
Create Date: 2026-02-09
"""

from alembic import op


revision = "b2c3d4e5fix"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create indexes directly without batch_alter_table
    # This avoids the DROP TABLE issues
    
    op.execute('CREATE INDEX IF NOT EXISTS idx_files_library_id ON files (library_id)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_files_identified ON files (identified)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_files_size ON files (size)')
    
    op.execute('CREATE INDEX IF NOT EXISTS idx_titles_up_to_date_have_base ON titles (up_to_date, have_base)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_titles_have_base ON titles (have_base)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_titles_up_to_date ON titles (up_to_date)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_titles_have_base_added_at ON titles (have_base, added_at)')
    
    op.execute('CREATE INDEX IF NOT EXISTS idx_apps_title_id_owned ON apps (title_id, owned)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_apps_title_id_type_owned ON apps (title_id, app_type, owned)')


def downgrade():
    # Drop indexes created by this migration
    op.execute('DROP INDEX IF EXISTS idx_apps_title_id_type_owned')
    op.execute('DROP INDEX IF EXISTS idx_apps_title_id_owned')
    op.execute('DROP INDEX IF EXISTS idx_titles_have_base_added_at')
    op.execute('DROP INDEX IF EXISTS idx_titles_up_to_date')
    op.execute('DROP INDEX IF EXISTS idx_titles_have_base')
    op.execute('DROP INDEX IF EXISTS idx_titles_up_to_date_have_base')
    op.execute('DROP INDEX IF EXISTS idx_files_size')
    op.execute('DROP INDEX IF EXISTS idx_files_identified')
    op.execute('DROP INDEX IF EXISTS idx_files_library_id')
'''

# Write the migration file
migration_path = "app/migrations/versions/b2c3d4e5fix_create_indexes_fixed.py"
with open(migration_path, "w") as f:
    f.write(migration_content)

print(f"✓ Migration file created: {migration_path}")
print("✓ This migration creates indexes without modifying table structure")
print("✓ Use revision 'b2c3d4e5fix' to apply it safely")
