"""
Repository for Wishlist database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.wishlist import Wishlist


class WishlistRepository:
    """Repository for Wishlist database operations"""

    @staticmethod
    def get_all():
        """Get all Wishlist records"""
        return Wishlist.query.all()

    @staticmethod
    def get_by_id(id):
        """Get Wishlist by ID"""
        return Wishlist.query.get(id)

    @staticmethod
    def get_by_user_and_id(user_id, id):
        """Get Wishlist item for a specific user and ID"""
        return Wishlist.query.filter_by(user_id=user_id, id=id).first()

    @staticmethod
    def get_by_title_id(title_id):
        """Get Wishlist item by TitleID"""
        return Wishlist.query.filter_by(title_id=title_id).first()

    @staticmethod
    def get_by_user_and_title(user_id, title_id):
        """Get Wishlist item for a specific user and TitleID"""
        return Wishlist.query.filter_by(user_id=user_id, title_id=title_id).first()

    @staticmethod
    def get_all_by_user(user_id):
        """Get all Wishlist records for a user"""
        return Wishlist.query.filter_by(user_id=user_id).order_by(Wishlist.added_date.desc()).all()

    @staticmethod
    def create(**kwargs):
        """Create new Wishlist record"""
        try:
            item = Wishlist(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e

    @staticmethod
    def update(id, **kwargs):
        """Update Wishlist record"""
        item = Wishlist.query.get(id)
        if not item:
            return None

        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)

        db.session.commit()
        return item

    @staticmethod
    def delete(id):
        """Delete Wishlist record"""
        item = Wishlist.query.get(id)
        if not item:
            return False

        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total Wishlist records"""
        return Wishlist.query.count()
