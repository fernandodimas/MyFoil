"""
Repository for Libraries database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy import func
from db import db, Files, Apps, app_files
from models.libraries import Libraries


class LibrariesRepository:
    """Repository for Libraries database operations"""

    @staticmethod
    def get_all():
        """Get all Libraries records"""
        return Libraries.query.all()

    @staticmethod
    def get_all_with_stats():
        """Get all Libraries records with file/title counts and total size"""
        libs = Libraries.query.all()
        results = []

        for l in libs:
            files_count = Files.query.filter_by(library_id=l.id).count()
            total_size = db.session.query(func.sum(Files.size)).filter_by(library_id=l.id).scalar() or 0

            # Use subquery to avoid select_from conflict
            try:
                subquery = (
                    db.session.query(Apps.title_id)
                    .distinct()
                    .join(app_files, Apps.id == app_files.c.app_id)
                    .join(Files, Files.id == app_files.c.file_id)
                    .filter(Files.library_id == l.id)
                )
                titles_count = subquery.count()
            except Exception:
                titles_count = 0

            results.append(
                {"library": l, "files_count": files_count, "total_size": total_size, "titles_count": titles_count}
            )
        return results

    @staticmethod
    def get_by_id(id):
        """Get Libraries by ID"""
        return Libraries.query.get(id)

    @staticmethod
    def create(**kwargs):
        """Create new Libraries record"""
        try:
            item = Libraries(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e

    @staticmethod
    def update(id, **kwargs):
        """Update Libraries record"""
        item = Libraries.query.get(id)
        if not item:
            return None
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        db.session.commit()
        return item

    @staticmethod
    def delete(id):
        """Delete Libraries record"""
        item = Libraries.query.get(id)
        if not item:
            return False
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total Libraries records"""
        return Libraries.query.count()
