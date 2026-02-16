"""create user_title_flags table

Revision ID: zz_add_user_title_flags
Revises:
Create Date: 2026-02-13 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "zz_add_user_title_flags"
down_revision = "d3f4e5a6b7c8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_title_flags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("title_id", sa.String(), nullable=False, index=True),
        sa.Column("has_non_ignored_dlcs", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("has_non_ignored_updates", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("has_non_ignored_redundant", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_user_title_flags_user_title", "user_title_flags", ["user_id", "title_id"])


def downgrade():
    op.drop_index("ix_user_title_flags_user_title", table_name="user_title_flags")
    op.drop_table("user_title_flags")
