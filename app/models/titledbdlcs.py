"""
Model: TitleDBDLCs
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db, now_utc
from flask_login import UserMixin


class TitleDBDLCs(db.Model):
    __tablename__ = "titledb_dlcs"

    id = db.Column(db.Integer, primary_key=True)
    base_title_id = db.Column(db.String(16), nullable=False, index=True)
    dlc_app_id = db.Column(db.String(16), nullable=False, index=True)

    __table_args__ = (
        db.Index("idx_dlc_base", "base_title_id"),
        db.Index("idx_dlc_app", "dlc_app_id"),
    )
