"""Add titledb_version column to Files table for tracking TitleDB updates

Revision ID: c3d4e5f8a12
Revises: b2c3d4e5f8a1

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c3d4e5f8a12"
down_revision = "b2c3d4e5f8a1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE files ADD COLUMN titledb_version VARCHAR
    """)


def downgrade():
    op.execute("""
        ALTER TABLE files DROP COLUMN titledb_version
    """)
