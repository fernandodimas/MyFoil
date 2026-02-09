"""
Repository for TitleDBVersions database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.titledbversions import TitleDBVersions


class TitleDBVersionsRepository:
    """Repository for TitleDBVersions database operations"""
    
    @staticmethod
    def get_all():
        """Get all TitleDBVersions records"""
        return TitleDBVersions.query.all()
    
    @staticmethod
    def get_by_id(id):
        """Get TitleDBVersions by ID"""
        return TitleDBVersions.query.get(id)
    
    @staticmethod
    def create(**kwargs):
        """Create new TitleDBVersions record"""
        try:
            item = TitleDBVersions(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def update(id, **kwargs):
        """Update TitleDBVersions record"""
        item = TitleDBVersions.query.get(id)
        if not item:
            return None
        
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        db.session.commit()
        return item
    
    @staticmethod
    def delete(id):
        """Delete TitleDBVersions record"""
        item = TitleDBVersions.query.get(id)
        if not item:
            return False
        
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total TitleDBVersions records"""
        return TitleDBVersions.query.count()
