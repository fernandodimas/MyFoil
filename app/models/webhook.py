"""
Model: Webhook
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db, now_utc
from flask_login import UserMixin

class Webhook(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    events = db.Column(db.Text)  # JSON list: ['file_added', 'scan_complete']
    secret = db.Column(db.String(100))
    active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        import json

        return {
            "id": self.id,
            "url": self.url,
            "events": json.loads(self.events) if self.events else [],
            "secret": self.secret,
            "active": self.active,
        }


