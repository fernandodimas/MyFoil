"""
Model: Apps
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db

# Association table for many-to-many relationship between Apps and Files
app_files = db.Table(
    "app_files",
    db.Column("app_id", db.Integer, db.ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True),
    db.Column("file_id", db.Integer, db.ForeignKey("files.id", ondelete="CASCADE"), primary_key=True),
)


class Apps(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title_id = db.Column(db.Integer, db.ForeignKey("titles.id", ondelete="CASCADE"), nullable=False)
    app_id = db.Column(db.String, index=True)  # Index for faster lookups
    app_version = db.Column(db.BigInteger)
    app_type = db.Column(db.String, index=True)  # Index for filtering by type
    owned = db.Column(db.Boolean, default=False, index=True)  # Index for owned filter

    title = db.relationship("Titles", backref=db.backref("apps", lazy=True, cascade="all, delete-orphan"))
    files = db.relationship("Files", secondary=app_files, backref=db.backref("apps", lazy="select"))

    __table_args__ = (
        db.UniqueConstraint("app_id", "app_version", name="uq_apps_app_version"),
        # Composite index for common query patterns
        db.Index("idx_app_id_version", "app_id", "app_version"),
        db.Index("idx_owned_type", "owned", "app_type"),
        db.Index("idx_title_type", "title_id", "app_type"),
    )
