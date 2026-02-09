"""
Model: TitleDBCache
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db, now_utc
from flask_login import UserMixin

class TitleDBCache(db.Model):
    __tablename__ = "titledb_cache"

    id = db.Column(db.Integer, primary_key=True)
    title_id = db.Column(db.String(16), unique=True, nullable=False, index=True)
    data = db.Column(db.JSON, nullable=False)  # Full title data as JSON
    source = db.Column(db.String(50), nullable=False)  # 'titles.json', 'US.en.json', 'BR.pt.json', etc.
    downloaded_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_utc, onupdate=now_utc)

    # Indexes for fast lookups
    __table_args__ = (db.Index("idx_source", "source"),)


