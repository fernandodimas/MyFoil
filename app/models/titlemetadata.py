"""
Model: TitleMetadata
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db, now_utc
from flask_login import UserMixin

class TitleMetadata(db.Model):
    """Remote metadata for titles from external sources (RAWG, IGDB, etc)"""

    __tablename__ = "title_metadata"

    id = db.Column(db.Integer, primary_key=True)
    title_id = db.Column(
        db.String(16), db.ForeignKey("titles.title_id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Metadata fields
    description = db.Column(db.Text)
    rating = db.Column(db.Float)  # normalized 0-100
    rating_count = db.Column(db.Integer)
    genres = db.Column(db.JSON)  # list of strings
    tags = db.Column(db.JSON)  # list of strings
    release_date = db.Column(db.Date)

    # Media URLs
    cover_url = db.Column(db.String(512))
    banner_url = db.Column(db.String(512))
    screenshots = db.Column(db.JSON)  # list of URLs

    # Source tracking
    source = db.Column(db.String(50))  # 'rawg', 'igdb', 'nintendo'
    source_id = db.Column(db.String(100))  # ID in source system

    # Timestamps
    fetched_at = db.Column(db.DateTime, default=now_utc)
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)

    # Relationship handled by backref on metadata_entries

    __table_args__ = (db.UniqueConstraint("title_id", "source", name="uq_title_source"),)


