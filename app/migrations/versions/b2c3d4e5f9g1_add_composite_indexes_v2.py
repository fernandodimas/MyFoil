"""Add composite indexes for performance optimization (Phase 2.1)

Adds indexes to optimize:
- Stats queries (routes/library.py:383-404)
- Outdated games query (routes/library.py:298)
- Metadata filtering (metadata_service.py:60-82)
- File size queries

Revision ID: b2c3d4e5f9g1
Revises: c3d4e5f8a12

"""

from alembic import op


revision = "b2c3d4e5f9g1"
down_revision = "c3d4e5f8a12"
branch_labels = None
depends_on = None


def upgrade():
    # === FILES indexes ===
    with op.batch_alter_table("files", schema=None) as batch_op:
        # Individual indexes for single-column queries (used in stats)
        batch_op.create_index("idx_files_library_id", ["library_id"], unique=False)
        batch_op.create_index("idx_files_identified", ["identified"], unique=False)

        # Index for size-based queries
        batch_op.create_index("idx_files_size", ["size"], unique=False)

    # === TITLES indexes ===
    with op.batch_alter_table("titles", schema=None) as batch_op:
        # Composite index for outdated games query (up_to_date=False AND have_base=True)
        batch_op.create_index("idx_titles_up_to_date_have_base", ["up_to_date", "have_base"], unique=False)

        # Individual indexes for titles filtering
        batch_op.create_index("idx_titles_have_base", ["have_base"], unique=False)
        batch_op.create_index("idx_titles_up_to_date", ["up_to_date"], unique=False)

        # Composite index for metadata filtering (have_base + added_at)
        batch_op.create_index("idx_titles_have_base_added_at", ["have_base", "added_at"], unique=False)

    # === APPS indexes ===
    with op.batch_alter_table("apps", schema=None) as batch_op:
        # Composite index for finding owned apps by title (used in outdated games)
        batch_op.create_index("idx_apps_title_id_owned", ["title_id", "owned"], unique=False)

        # Additional composite index for title/app_type/owned pattern (N+1 prevention)
        batch_op.create_index("idx_apps_title_id_type_owned", ["title_id", "app_type", "owned"], unique=False)

        # Note: idx_owned_type and idx_title_type already exist from migration 9207770128d9


def downgrade():
    # === APPS indexes ===
    with op.batch_alter_table("apps", schema=None) as batch_op:
        batch_op.drop_index("idx_apps_title_id_type_owned")
        batch_op.drop_index("idx_apps_title_id_owned")

    # === TITLES indexes ===
    with op.batch_alter_table("titles", schema=None) as batch_op:
        batch_op.drop_index("idx_titles_have_base_added_at")
        batch_op.drop_index("idx_titles_up_to_date")
        batch_op.drop_index("idx_titles_have_base")
        batch_op.drop_index("idx_titles_up_to_date_have_base")

    # === FILES indexes ===
    with op.batch_alter_table("files", schema=None) as batch_op:
        batch_op.drop_index("idx_files_size")
        batch_op.drop_index("idx_files_identified")
        batch_op.drop_index("idx_files_library_id")
