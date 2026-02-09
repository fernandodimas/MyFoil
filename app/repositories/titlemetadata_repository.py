"""
Repository for TitleMetadata database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.titlemetadata import TitleMetadata


class TitleMetadataRepository:
    """Repository for TitleMetadata database operations"""
    
    @staticmethod
    def get_all():
        """Get all TitleMetadata records"""
        return TitleMetadata.query.all()
    
    @staticmethod
    def get_by_id(id):
        """Get TitleMetadata by ID"""
        return TitleMetadata.query.get(id)
    
    @staticmethod
    def create(**kwargs):
        """Create new TitleMetadata record"""
        try:
            item = TitleMetadata(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def update(id, **kwargs):
        """Update TitleMetadata record"""
        item = TitleMetadata.query.get(id)
        if not item:
            return None
        
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        db.session.commit()
        return item
    
    @staticmethod
    def delete(id):
        """Delete TitleMetadata record"""
        item = TitleMetadata.query.get(id)
        if not item:
            return False
        
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total TitleMetadata records"""
        return TitleMetadata.query.count()
