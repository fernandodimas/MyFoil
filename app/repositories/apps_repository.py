"""
Repository for Apps database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy import func, and_, case
from sqlalchemy.exc import SQLAlchemyError
from db import db, app_files
from models.apps import Apps
from models.files import Files
from constants import APP_TYPE_BASE, APP_TYPE_UPD, APP_TYPE_DLC


class AppsRepository:
    """Repository for Apps database operations"""

    @staticmethod
    def get_all():
        """Get all Apps records"""
        return Apps.query.all()

    @staticmethod
    def get_by_id(id):
        """Get Apps by ID"""
        return db.session.get(Apps, id)

    @staticmethod
    def get_by_app_id(app_id, owned=None):
        """Get Apps by its hex string AppID"""
        query = Apps.query.filter(Apps.app_id.ilike(app_id))
        if owned is not None:
            query = query.filter(Apps.owned == owned)
        return query.first()

    @staticmethod
    def get_all_by_title_id(title_id):
        """Get all apps for a specific title (hex ID)"""
        return Apps.query.filter(Apps.title_id.ilike(title_id)).all()

    @staticmethod
    def get_owned_by_title(title_pk):
        """Get all owned apps for a specific title primary key"""
        return Apps.query.filter_by(title_id=title_pk, owned=True).all()

    @staticmethod
    def get_owned_counts(library_id=None):
        """
        Count owned bases, updates, and DLCs
        """
        query = db.session.query(
            func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_BASE), 1), else_=0)).label("bases"),
            func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_UPD), 1), else_=0)).label("updates"),
            func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_DLC), 1), else_=0)).label("dlcs"),
            func.count(func.distinct(case((Apps.owned == True, Apps.title_id), else_=None))).label("distinct_titles"),
        )

        if library_id:
            query = query.join(app_files).join(Files).filter(Files.library_id == library_id)

        stats = query.first()
        if not stats:
            return {"bases": 0, "updates": 0, "dlcs": 0, "distinct_titles": 0}

        return {
            "bases": stats.bases or 0,
            "updates": stats.updates or 0,
            "dlcs": stats.dlcs or 0,
            "distinct_titles": stats.distinct_titles or 0,
        }

    @staticmethod
    def get_orphaned_owned():
        """Get owned apps with no associated files"""
        # Optimized query using ~Any or NOT EXISTS
        return Apps.query.filter(Apps.owned == True).filter(~Apps.files.any()).all()

    @staticmethod
    def create(**kwargs):
        """Create new Apps record"""
        try:
            item = Apps(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e

    @staticmethod
    def update(id, **kwargs):
        """Update Apps record"""
        item = Apps.query.get(id)
        if not item:
            return None

        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)

        db.session.commit()
        return item

    @staticmethod
    def delete(id):
        """Delete Apps record"""
        item = Apps.query.get(id)
        if not item:
            return False

        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total Apps records"""
        return Apps.query.count()
