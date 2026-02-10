"""
Repository for Libraries database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.libraries import Libraries


class LibrariesRepository:
    """Repository for Libraries database operations"""

    @staticmethod
    def get_all():
        """Get all Libraries records"""
        return Libraries.query.all()

    @staticmethod
    def get_by_id(id):
        """Get Libraries by ID"""
        return Libraries.query.get(id)

    @staticmethod
    def create(**kwargs):
        """Create new Libraries record"""
        try:
            item = Libraries(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e

    @staticmethod
    def update(id, **kwargs):
        """Update Libraries record"""
        item = Libraries.query.get(id)
        if not item:
            return None
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        db.session.commit()
        return item

    @staticmethod
    def delete(id):
        """Delete Libraries record"""
        item = Libraries.query.get(id)
        if not item:
            return False
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total Libraries records"""
        return Libraries.query.count()
