"""
Repository for Titles database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.titles import Titles


class TitlesRepository:
    """Repository for Titles database operations"""
    
    @staticmethod
    def get_all():
        """Get all Titles records"""
        return Titles.query.all()
    
    @staticmethod
    def get_by_id(id):
        """Get Titles by ID"""
        return Titles.query.get(id)
    
    @staticmethod
    def create(**kwargs):
        """Create new Titles record"""
        try:
            item = Titles(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def update(id, **kwargs):
        """Update Titles record"""
        item = Titles.query.get(id)
        if not item:
            return None
        
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        db.session.commit()
        return item
    
    @staticmethod
    def delete(id):
        """Delete Titles record"""
        item = Titles.query.get(id)
        if not item:
            return False
        
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total Titles records"""
        return Titles.query.count()
