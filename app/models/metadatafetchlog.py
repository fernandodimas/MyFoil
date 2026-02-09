"""
Model: MetadataFetchLog
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db, now_utc
from flask_login import UserMixin

class MetadataFetchLog(db.Model):
    """Execution log for metadata fetch jobs"""

    __tablename__ = "metadata_fetch_log"

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    completed_at = db.Column(db.DateTime)
    status = db.Column(db.String(20))  # 'running', 'completed', 'failed'

    titles_processed = db.Column(db.Integer, default=0)
    titles_updated = db.Column(db.Integer, default=0)
    titles_failed = db.Column(db.Integer, default=0)

    error_message = db.Column(db.Text)


