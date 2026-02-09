"""
Model: Tag
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db, now_utc
from flask_login import UserMixin

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(7))  # Hex color
    icon = db.Column(db.String(50))  # Bootstrap/FontAwesome icon class


