"""
Repository for Files database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.files import Files


class FilesRepository:
    """Repository for Files database operations"""
    
    @staticmethod
    def get_all():
        """Get all Files records"""
        return Files.query.all()
    
    @staticmethod
    def get_by_id(id):
        """Get Files by ID"""
        return Files.query.get(id)
    
    @staticmethod
    def create(**kwargs):
        """Create new Files record"""
        try:
            item = Files(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def update(id, **kwargs):
        """Update Files record"""
        item = Files.query.get(id)
        if not item:
            return None
        
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        db.session.commit()
        return item
    
    @staticmethod
    def delete(id):
        """Delete Files record"""
        item = Files.query.get(id)
        if not item:
            return False
        
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total Files records"""
        return Files.query.count()
