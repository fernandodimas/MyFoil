"""
Repository for ActivityLog database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.activitylog import ActivityLog


class ActivityLogRepository:
    """Repository for ActivityLog database operations"""
    
    @staticmethod
    def get_all():
        """Get all ActivityLog records"""
        return ActivityLog.query.all()
    
    @staticmethod
    def get_by_id(id):
        """Get ActivityLog by ID"""
        return ActivityLog.query.get(id)
    
    @staticmethod
    def create(**kwargs):
        """Create new ActivityLog record"""
        try:
            item = ActivityLog(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def update(id, **kwargs):
        """Update ActivityLog record"""
        item = ActivityLog.query.get(id)
        if not item:
            return None
        
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        db.session.commit()
        return item
    
    @staticmethod
    def delete(id):
        """Delete ActivityLog record"""
        item = ActivityLog.query.get(id)
        if not item:
            return False
        
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total ActivityLog records"""
        return ActivityLog.query.count()
