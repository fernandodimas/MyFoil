"""
Libraries model - represents a library path in the filesystem.
"""

from db import db


class Libraries(db.Model):
    """Library model representing a directory containing Switch game files."""

    __tablename__ = "libraries"

    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String, unique=True, nullable=False)
    last_scan = db.Column(db.DateTime)

    def __repr__(self):
        return f"<Libraries(id={self.id}, path={self.path})>"
