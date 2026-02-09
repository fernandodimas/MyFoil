"""
Repository for MetadataFetchLog database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.metadatafetchlog import MetadataFetchLog


class MetadataFetchLogRepository:
    """Repository for MetadataFetchLog database operations"""
    
    @staticmethod
    def get_all():
        """Get all MetadataFetchLog records"""
        return MetadataFetchLog.query.all()
    
    @staticmethod
    def get_by_id(id):
        """Get MetadataFetchLog by ID"""
        return MetadataFetchLog.query.get(id)
    
    @staticmethod
    def create(**kwargs):
        """Create new MetadataFetchLog record"""
        try:
            item = MetadataFetchLog(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def update(id, **kwargs):
        """Update MetadataFetchLog record"""
        item = MetadataFetchLog.query.get(id)
        if not item:
            return None
        
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        db.session.commit()
        return item
    
    @staticmethod
    def delete(id):
        """Delete MetadataFetchLog record"""
        item = MetadataFetchLog.query.get(id)
        if not item:
            return False
        
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total MetadataFetchLog records"""
        return MetadataFetchLog.query.count()
