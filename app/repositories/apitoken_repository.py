"""
Repository for ApiToken database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from db import db
from models.apitoken import ApiToken


class ApiTokenRepository:
    """Repository for ApiToken database operations"""

    @staticmethod
    def get_all():
        """Get all ApiToken records with user info"""
        return ApiToken.query.options(joinedload(ApiToken.user)).all()

    @staticmethod
    def get_by_id(id):
        """Get ApiToken by ID"""
        return ApiToken.query.get(id)

    @staticmethod
    def create(**kwargs):
        """Create new ApiToken record"""
        try:
            item = ApiToken(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e

    @staticmethod
    def update(id, **kwargs):
        """Update ApiToken record"""
        item = ApiToken.query.get(id)
        if not item:
            return None

        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)

        db.session.commit()
        return item

    @staticmethod
    def delete(id):
        """Delete ApiToken record"""
        item = ApiToken.query.get(id)
        if not item:
            return False

        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total ApiToken records"""
        return ApiToken.query.count()
