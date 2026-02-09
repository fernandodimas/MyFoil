"""
Repository for TitleTag database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.titletag import TitleTag


class TitleTagRepository:
    """Repository for TitleTag database operations"""
    
    @staticmethod
    def get_all():
        """Get all TitleTag records"""
        return TitleTag.query.all()
    
    @staticmethod
    def get_by_id(id):
        """Get TitleTag by ID"""
        return TitleTag.query.get(id)
    
    @staticmethod
    def create(**kwargs):
        """Create new TitleTag record"""
        try:
            item = TitleTag(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def update(id, **kwargs):
        """Update TitleTag record"""
        item = TitleTag.query.get(id)
        if not item:
            return None
        
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        db.session.commit()
        return item
    
    @staticmethod
    def delete(id):
        """Delete TitleTag record"""
        item = TitleTag.query.get(id)
        if not item:
            return False
        
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total TitleTag records"""
        return TitleTag.query.count()
