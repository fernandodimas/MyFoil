"""
Repository for SystemJob database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.systemjob import SystemJob


class SystemJobRepository:
    """Repository for SystemJob database operations"""

    @staticmethod
    def get_all():
        """Get all SystemJob records"""
        return SystemJob.query.all()

    @staticmethod
    def get_by_id(id):
        """Get SystemJob by ID"""
        return db.session.get(SystemJob, id)

    @staticmethod
    def is_job_type_running(job_type):
        """Check if a specific job type is currently running"""
        return SystemJob.query.filter(SystemJob.job_type == job_type, SystemJob.status == "running").first() is not None

    @staticmethod
    def is_metadata_job_running():
        """Check if any metadata-related job is running"""
        return (
            SystemJob.query.filter(SystemJob.job_type.like("%metadata_fetch%"), SystemJob.status == "running").first()
            is not None
        )

    @staticmethod
    def create(**kwargs):
        """Create new SystemJob record"""
        try:
            item = SystemJob(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e

    @staticmethod
    def update(id, **kwargs):
        """Update SystemJob record"""
        item = SystemJob.query.get(id)
        if not item:
            return None

        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)

        db.session.commit()
        return item

    @staticmethod
    def delete(id):
        """Delete SystemJob record"""
        item = SystemJob.query.get(id)
        if not item:
            return False

        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total SystemJob records"""
        return SystemJob.query.count()
