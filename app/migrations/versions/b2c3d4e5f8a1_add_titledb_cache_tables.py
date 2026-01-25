"""Add TitleDB cache tables for fast lookups

Revision ID: b2c3d4e5f8a1
Revises: a1b2c3d4e5f7

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f8a1"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS titledb_cache (
            id INTEGER PRIMARY KEY,
            title_id VARCHAR(16) UNIQUE NOT NULL,
            data JSON NOT NULL,
            source VARCHAR(50) NOT NULL,
            downloaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_source ON titledb_cache (source)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS titledb_versions (
            id INTEGER PRIMARY KEY,
            title_id VARCHAR(16) NOT NULL,
            version INTEGER NOT NULL,
            release_date VARCHAR(8)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_title_version ON titledb_versions (title_id, version)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS titledb_dlcs (
            id INTEGER PRIMARY KEY,
            base_title_id VARCHAR(16) NOT NULL,
            dlc_app_id VARCHAR(16) NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_dlc_base ON titledb_dlcs (base_title_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_dlc_app ON titledb_dlcs (dlc_app_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS titledb_dlcs")
    op.execute("DROP TABLE IF EXISTS titledb_versions")
    op.execute("DROP TABLE IF EXISTS titledb_cache")
