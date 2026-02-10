"""
Repository for TitleMetadata database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from db import db
from models.titlemetadata import TitleMetadata


class TitleMetadataRepository:
    """Repository for TitleMetadata database operations"""

    @staticmethod
    def get_by_title_id(title_id):
        """Get TitleMetadata by TitleID"""
        return TitleMetadata.query.filter_by(title_id=title_id).all()

    @staticmethod
    def delete_by_title_id(title_id):
        """Delete all metadata for a title"""
        TitleMetadata.query.filter_by(title_id=title_id).delete()
        db.session.commit()
