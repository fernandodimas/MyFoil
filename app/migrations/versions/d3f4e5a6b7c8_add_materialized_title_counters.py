"""Add materialized counters to Titles for redundant updates and missing DLCs

Revision ID: d3f4e5a6b7c8
Revises: a1b2c3d4e5f6

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d3f4e5a6b7c8"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("titles", schema=None) as batch_op:
        # Add integer counters with default 0 to avoid NULL checks in queries
        batch_op.add_column(sa.Column("redundant_updates_count", sa.Integer(), nullable=True, server_default="0"))
        batch_op.add_column(sa.Column("missing_dlcs_count", sa.Integer(), nullable=True, server_default="0"))
        # Create indexes to speed up filters
        batch_op.create_index("idx_titles_redundant_updates_count", ["redundant_updates_count"], unique=False)
        batch_op.create_index("idx_titles_missing_dlcs_count", ["missing_dlcs_count"], unique=False)


def downgrade():
    with op.batch_alter_table("titles", schema=None) as batch_op:
        try:
            batch_op.drop_index("idx_titles_missing_dlcs_count")
        except Exception:
            pass
        try:
            batch_op.drop_index("idx_titles_redundant_updates_count")
        except Exception:
            pass

        try:
            batch_op.drop_column("missing_dlcs_count")
        except Exception:
            pass
        try:
            batch_op.drop_column("redundant_updates_count")
        except Exception:
            pass
