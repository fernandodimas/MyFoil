"""
Model: Webhook
Lightweight model to keep compatibility with existing repository and routes.
"""

from db import db


class Webhook(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(1024))
    event = db.Column(db.String(100))
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "event": self.event,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
