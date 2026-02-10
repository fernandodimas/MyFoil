"""
Repository for Tag database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.tag import Tag


class TagRepository:
    """Repository for Tag database operations"""

    @staticmethod
    def get_all():
        """Get all Tag records"""
        return Tag.query.all()

    @staticmethod
    def get_by_id(id):
        """Get Tag by ID"""
        return Tag.query.get(id)

    @staticmethod
    def get_by_ids(ids):
        """Get Tags by a list of IDs"""
        return Tag.query.filter(Tag.id.in_(ids)).all()

    @staticmethod
    def create(**kwargs):
        """Create new Tag record"""
        try:
            item = Tag(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e

    @staticmethod
    def update(id, **kwargs):
        """Update Tag record"""
        item = Tag.query.get(id)
        if not item:
            return None

        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)

        db.session.commit()
        return item

    @staticmethod
    def delete(id):
        """Delete Tag record"""
        item = Tag.query.get(id)
        if not item:
            return False

        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total Tag records"""
        return Tag.query.count()
