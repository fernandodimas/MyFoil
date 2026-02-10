"""
Repository for Files database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy import func, case
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.files import Files
from models.apps import Apps


class FilesRepository:
    """Repository for Files database operations"""

    @staticmethod
    def get_all():
        """Get all Files records"""
        return Files.query.all()

    @staticmethod
    def get_by_id(id):
        """Get Files by ID"""
        return db.session.get(Files, id)

    @staticmethod
    def get_all_optimized():
        """Get all files with eager loading of apps and titles"""
        return Files.query.options(joinedload(Files.apps).joinedload(Apps.title)).order_by(Files.filename).all()

    @staticmethod
    def get_unidentified_or_error():
        """Get files that are not identified or have an error"""
        return Files.query.filter((Files.identified == False) | (Files.identification_error.isnot(None))).all()

    @staticmethod
    def get_identified_unknown_titles():
        """Get identified files where the title name is unknown"""
        return (
            Files.query.join(Files.apps)
            .join(Apps.title)
            .filter(Files.identified == True)
            .filter(db.or_(Apps.title.name.is_(None), Apps.title.name.ilike("Unknown%")))
            .all()
        )

    @staticmethod
    def get_stats_by_library(library_id=None):
        """
        Get aggregated file statistics (total count, size, unidentified)
        """
        query = db.session.query(
            func.count(Files.id).label("total_files"),
            func.sum(Files.size).label("total_size"),
            func.sum(case((Files.identified == False, 1), else_=0)).label("unidentified_files"),
        )

        if library_id:
            query = query.filter(Files.library_id == library_id)

        stats = query.first()
        return {
            "total_files": stats.total_files or 0,
            "total_size": stats.total_size or 0,
            "unidentified_files": stats.unidentified_files or 0,
        }

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
