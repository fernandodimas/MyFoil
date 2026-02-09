"""
Repository for TitleDBDLCs database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.titledbdlcs import TitleDBDLCs


class TitleDBDLCsRepository:
    """Repository for TitleDBDLCs database operations"""
    
    @staticmethod
    def get_all():
        """Get all TitleDBDLCs records"""
        return TitleDBDLCs.query.all()
    
    @staticmethod
    def get_by_id(id):
        """Get TitleDBDLCs by ID"""
        return TitleDBDLCs.query.get(id)
    
    @staticmethod
    def create(**kwargs):
        """Create new TitleDBDLCs record"""
        try:
            item = TitleDBDLCs(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def update(id, **kwargs):
        """Update TitleDBDLCs record"""
        item = TitleDBDLCs.query.get(id)
        if not item:
            return None
        
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        db.session.commit()
        return item
    
    @staticmethod
    def delete(id):
        """Delete TitleDBDLCs record"""
        item = TitleDBDLCs.query.get(id)
        if not item:
            return False
        
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total TitleDBDLCs records"""
        return TitleDBDLCs.query.count()
