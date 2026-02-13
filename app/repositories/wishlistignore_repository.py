"""
Repository for WishlistIgnore database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.wishlistignore import WishlistIgnore
import json
import functools


class WishlistIgnoreRepository:
    """Repository for WishlistIgnore database operations"""

    @staticmethod
    def get_all():
        """Get all WishlistIgnore records"""
        return WishlistIgnore.query.all()

    @staticmethod
    def get_by_id(id):
        """Get WishlistIgnore by ID"""
        return db.session.get(WishlistIgnore, id)

    @staticmethod
    def get_by_user_and_title(user_id, title_id):
        """Get ignore preferences for a specific user and title"""
        return WishlistIgnore.query.filter_by(user_id=user_id, title_id=title_id).first()

    @staticmethod
    def get_all_by_user(user_id):
        """Get all ignore preferences for a user"""
        return WishlistIgnore.query.filter_by(user_id=user_id).all()


# Cached flattened view per-user: { title_id: { 'dlcs': set(UPPER_APP_IDs), 'updates': set(version_strs) } }
@functools.lru_cache(maxsize=128)
def get_flattened_ignores_for_user(user_id):
    try:
        records = WishlistIgnore.query.filter_by(user_id=user_id).all()
        result = {}
        for rec in records:
            try:
                dlcs = json.loads(rec.ignore_dlcs) if rec.ignore_dlcs else {}
            except Exception:
                dlcs = {}
            try:
                updates = json.loads(rec.ignore_updates) if rec.ignore_updates else {}
            except Exception:
                updates = {}

            # Normalize to sets for fast membership checks
            result[rec.title_id] = {
                "dlcs": set(k.upper() for k, v in dlcs.items() if v),
                "updates": set(str(k) for k, v in updates.items() if v),
            }
        return result
    except Exception:
        return {}

    @staticmethod
    def create(**kwargs):
        """Create new WishlistIgnore record"""
        try:
            item = WishlistIgnore(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            # Invalidate flattened cache for this user
            try:
                get_flattened_ignores_for_user.cache_clear()
            except Exception:
                pass
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
        # Invalidate flattened cache for this user
        try:
            get_flattened_ignores_for_user.cache_clear()
        except Exception:
            pass
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
