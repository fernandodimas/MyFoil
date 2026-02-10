"""Activity log model.

This module intentionally only contains the SQLAlchemy model.
Database initialization and helper functions live in `app/db.py`.
"""

from db import db
from utils import now_utc


class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=now_utc, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    action_type = db.Column(db.String(50), index=True)
    title_id = db.Column(db.String, nullable=True)
    details = db.Column(db.Text)

    __table_args__ = (db.Index("idx_activity_timestamp_action", "timestamp", "action_type"),)
