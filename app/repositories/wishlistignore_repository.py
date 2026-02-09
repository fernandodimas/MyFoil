"""
Repository for WishlistIgnore database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.wishlistignore import WishlistIgnore


class WishlistIgnoreRepository:
    """Repository for WishlistIgnore database operations"""
    
    @staticmethod
    def get_all():
        """Get all WishlistIgnore records"""
        return WishlistIgnore.query.all()
    
    @staticmethod
    def get_by_id(id):
        """Get WishlistIgnore by ID"""
        return WishlistIgnore.query.get(id)
    
    @staticmethod
    def create(**kwargs):
        """Create new WishlistIgnore record"""
        try:
            item = WishlistIgnore(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def update(id, **kwargs):
        """Update WishlistIgnore record"""
        item = WishlistIgnore.query.get(id)
        if not item:
            return None
        
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        db.session.commit()
        return item
    
    @staticmethod
    def delete(id):
        """Delete WishlistIgnore record"""
        item = WishlistIgnore.query.get(id)
        if not item:
            return False
        
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total WishlistIgnore records"""
        return WishlistIgnore.query.count()
