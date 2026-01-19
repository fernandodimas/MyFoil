"""Add TitleDB cache tables for fast lookups

Revision ID: b2c3d4e5f8a1
Revises: a1b2c3d4e5f7

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.orm import sessionmaker

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f8a1"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade():
    # Create titledb_cache table
    op.create_table(
        "titledb_cache",
        Column("id", Integer, primary_key=True),
        Column("title_id", String(16), unique=True, nullable=False, index=True),
        Column("data", JSON, nullable=False),
        Column("source", String(50), nullable=False),
        Column("downloaded_at", DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        Column("updated_at", DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_source", "titledb_cache", ["source"])

    # Create titledb_versions table
    op.create_table(
        "titledb_versions",
        Column("id", Integer, primary_key=True),
        Column("title_id", String(16), nullable=False, index=True),
        Column("version", Integer, nullable=False),
        Column("release_date", String(8)),
    )
    op.create_index("idx_title_version", "titledb_versions", ["title_id", "version"])

    # Create titledb_dlcs table
    op.create_table(
        "titledb_dlcs",
        Column("id", Integer, primary_key=True),
        Column("base_title_id", String(16), nullable=False, index=True),
        Column("dlc_app_id", String(16), nullable=False, index=True),
    )
    op.create_index("idx_dlc_base", "titledb_dlcs", ["base_title_id"])
    op.create_index("idx_dlc_app", "titledb_dlcs", ["dlc_app_id"])


def downgrade():
    # Drop tables in reverse order
    op.drop_table("titledb_dlcs")
    op.drop_table("titledb_versions")
    op.drop_table("titledb_cache")
