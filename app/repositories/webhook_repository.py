"""
Repository for Webhook database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.webhook import Webhook


class WebhookRepository:
    """Repository for Webhook database operations"""
    
    @staticmethod
    def get_all():
        """Get all Webhook records"""
        return Webhook.query.all()
    
    @staticmethod
    def get_by_id(id):
        """Get Webhook by ID"""
        return Webhook.query.get(id)
    
    @staticmethod
    def create(**kwargs):
        """Create new Webhook record"""
        try:
            item = Webhook(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def update(id, **kwargs):
        """Update Webhook record"""
        item = Webhook.query.get(id)
        if not item:
            return None
        
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        db.session.commit()
        return item
    
    @staticmethod
    def delete(id):
        """Delete Webhook record"""
        item = Webhook.query.get(id)
        if not item:
            return False
        
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total Webhook records"""
        return Webhook.query.count()
