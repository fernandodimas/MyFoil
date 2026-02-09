"""
Model: TitleDBVersions
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db, now_utc
from flask_login import UserMixin

class TitleDBVersions(db.Model):
    __tablename__ = "titledb_versions"

    id = db.Column(db.Integer, primary_key=True)
    title_id = db.Column(db.String(16), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    release_date = db.Column(db.String(10))  # YYYY-MM-DD or YYYYMMDD

    __table_args__ = (db.Index("idx_title_version", "title_id", "version"),)


