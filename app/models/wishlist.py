"""
Model: Wishlist
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db, now_utc
from flask_login import UserMixin

class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"))
    title_id = db.Column(db.String, index=True)
    added_date = db.Column(db.DateTime, default=now_utc)
    priority = db.Column(db.Integer, default=0)  # 0-5
    notes = db.Column(db.Text)
    
    # Novos campos para tornar a wishlist independente do TitleDB
    name = db.Column(db.String)
    release_date = db.Column(db.String)
    icon_url = db.Column(db.String)
    banner_url = db.Column(db.String)
    description = db.Column(db.Text)
    genres = db.Column(db.String)         # JSON ou string separada por vírgulas
    screenshots = db.Column(db.Text)      # JSON list de URLs

    # Preferências de ignored (novas colunas)
    ignore_dlc = db.Column(db.Boolean, default=False)
    ignore_update = db.Column(db.Boolean, default=False)


