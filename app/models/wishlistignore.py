"""
Model: WishlistIgnore
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db, now_utc
from flask_login import UserMixin

class WishlistIgnore(db.Model):
    """Tabela para armazenar preferências de ignore da wishlist por usuário"""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=True)
    title_id = db.Column(db.String, index=True, nullable=False)
    ignore_dlcs = db.Column(db.Text, default="{}")  # JSON: {"app_id1": true, "app_id2": false, ...}
    ignore_updates = db.Column(db.Text, default="{}")  # JSON: {"v1": true, "v2": false, ...}
    created_at = db.Column(db.DateTime, default=now_utc)

    __table_args__ = (db.UniqueConstraint("user_id", "title_id", name="uix_user_title_ignore"),)


