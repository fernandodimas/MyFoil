"""
Model: ApiToken
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db, now_utc
from flask_login import UserMixin

class ApiToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc)
    last_used = db.Column(db.DateTime)

    user = db.relationship("User", backref=db.backref("api_tokens", lazy=True, cascade="all, delete-orphan"))


