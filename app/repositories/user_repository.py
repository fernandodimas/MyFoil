"""
Repository for User database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.user import User


class UserRepository:
    """Repository for User database operations"""
    
    @staticmethod
    def get_all():
        """Get all User records"""
        return User.query.all()
    
    @staticmethod
    def get_by_id(id):
        """Get User by ID"""
        return User.query.get(id)
    
    @staticmethod
    def create(**kwargs):
        """Create new User record"""
        try:
            item = User(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def update(id, **kwargs):
        """Update User record"""
        item = User.query.get(id)
        if not item:
            return None
        
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        db.session.commit()
        return item
    
    @staticmethod
    def delete(id):
        """Delete User record"""
        item = User.query.get(id)
        if not item:
            return False
        
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total User records"""
        return User.query.count()
