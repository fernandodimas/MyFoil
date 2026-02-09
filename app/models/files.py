"""
Model: Files
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db, now_utc
from flask_login import UserMixin

class Files(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    library_id = db.Column(db.Integer, db.ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False)
    filepath = db.Column(db.String, unique=True, nullable=False)
    folder = db.Column(db.String)
    filename = db.Column(db.String, nullable=False)
    extension = db.Column(db.String)
    size = db.Column(db.BigInteger)
    compressed = db.Column(db.Boolean, default=False)
    multicontent = db.Column(db.Boolean, default=False)
    nb_content = db.Column(db.Integer, default=0)
    download_count = db.Column(db.Integer, default=0)
    identified = db.Column(db.Boolean, default=False)
    identification_type = db.Column(db.String)
    identification_error = db.Column(db.String)
    identification_attempts = db.Column(db.Integer, default=0)
    last_attempt = db.Column(db.DateTime, default=now_utc)
    titledb_version = db.Column(db.String)  # TitleDB version when file was identified

    library = db.relationship("Libraries", backref=db.backref("files", lazy=True, cascade="all, delete-orphan"))

    __table_args__ = (
        # Composite index for library_id + identified queries (used in stats)
        db.Index("idx_files_library_identified", "library_id", "identified"),
        # Index for filepath lookups (helps with joins and lookups)
        db.Index("ix_files_filepath", "filepath"),
    )


