"""
Model: TitleTag
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db

class TitleTag(db.Model):
    title_id = db.Column(db.String, db.ForeignKey("titles.title_id", ondelete="CASCADE"), primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True)


