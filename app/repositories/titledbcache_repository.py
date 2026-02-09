"""
Repository for TitleDBCache database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.titledbcache import TitleDBCache


class TitleDBCacheRepository:
    """Repository for TitleDBCache database operations"""
    
    @staticmethod
    def get_all():
        """Get all TitleDBCache records"""
        return TitleDBCache.query.all()
    
    @staticmethod
    def get_by_id(id):
        """Get TitleDBCache by ID"""
        return TitleDBCache.query.get(id)
    
    @staticmethod
    def create(**kwargs):
        """Create new TitleDBCache record"""
        try:
            item = TitleDBCache(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def update(id, **kwargs):
        """Update TitleDBCache record"""
        item = TitleDBCache.query.get(id)
        if not item:
            return None
        
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        db.session.commit()
        return item
    
    @staticmethod
    def delete(id):
        """Delete TitleDBCache record"""
        item = TitleDBCache.query.get(id)
        if not item:
            return False
        
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total TitleDBCache records"""
        return TitleDBCache.query.count()
