"""
Repository for Titles database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.titles import Titles
from models.apps import Apps


class TitlesRepository:
    """Repository for Titles database operations"""

    @staticmethod
    def get_all():
        """Get all Titles records"""
        return Titles.query.all()

    @staticmethod
    def get_by_id(id):
        """Get Titles by primary key ID"""
        return db.session.get(Titles, id)

    @staticmethod
    def get_by_title_id(title_id):
        """Get Title by its hex string TitleID"""
        return Titles.query.filter(Titles.title_id.ilike(title_id)).first()

    @staticmethod
    def get_all_with_apps():
        """Get all titles with apps eagerly loaded"""
        return Titles.query.options(joinedload(Titles.apps)).all()

    @staticmethod
    def get_paged(page, per_page, sort_by="name", order="asc", query_text=None, filters=None):
        """
        Database-level pagination for titles
        """
        query = Titles.query.options(joinedload(Titles.apps)).filter(Titles.title_id.isnot(None))

        if query_text:
            query = query.filter(
                or_(
                    Titles.name.ilike(f"%{query_text}%"),
                    Titles.publisher.ilike(f"%{query_text}%"),
                    Titles.title_id.ilike(f"%{query_text}%"),
                )
            )

        if filters:
            if filters.get("owned_only"):
                query = query.filter(Titles.have_base == True)
            if filters.get("up_to_date"):
                query = query.filter(Titles.up_to_date == True)
            if filters.get("pending"):
                # pending means owned but not up_to_date
                query = query.filter(Titles.have_base == True, Titles.up_to_date == False)

            if filters.get("missing"):
                query = query.filter(or_(Titles.have_base == False, Titles.have_base == None))

            if filters.get("genre") and filters.get("genre") != "Todos os Gêneros":
                # Assuming JSON list stored as text, simple contains check
                g = filters.get("genre")
                query = query.filter(Titles.genres_json.ilike(f"%{g}%"))

            if filters.get("tag"):
                t = filters.get("tag")
                query = query.filter(Titles.tags_json.ilike(f"%{t}%"))

            if filters.get("dlc"):
                # DLC filter: Owned games that have missing DLCs (complete=False)
                query = query.filter(Titles.have_base == True, Titles.complete == False)

            if filters.get("redundant"):
                # Redundant filter: Games with more than 1 owned update file
                # We use a subquery to find title_ids (int PK) that have multiple owned updates
                subq = (
                    db.session.query(Apps.title_id)
                    .filter(Apps.app_type == "UPD", Apps.owned == True)
                    .group_by(Apps.title_id)
                    .having(func.count(Apps.id) > 1)
                    .subquery()
                )
                query = query.join(subq, Titles.id == subq.c.title_id)

        # Apply sorting
        sort_field = getattr(Titles, sort_by, Titles.name)
        if order == "desc":
            sort_field = sort_field.desc()
        query = query.order_by(sort_field)

        return query.paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_outdated(limit=100, offset=0):
        """Get titles that are not up to date but have base game"""
        return (
            Titles.query.filter(Titles.up_to_date == False, Titles.have_base == True).limit(limit).offset(offset).all()
        )

    @staticmethod
    def count_outdated():
        """Count total outdated titles"""
        return Titles.query.filter(Titles.up_to_date == False, Titles.have_base == True).count()

    @staticmethod
    def count_with_metadata():
        """Count games with enriched metadata"""
        return Titles.query.filter((Titles.metacritic_score.isnot(None)) | (Titles.rawg_rating.isnot(None))).count()

    @staticmethod
    def get_genre_distribution():
        """Get distribution of games by genre"""
        all_titles = Titles.query.filter(Titles.genres_json.isnot(None)).all()
        genre_dist = {}
        for t in all_titles:
            if t.genres_json:
                for g in t.genres_json:
                    genre_dist[g] = genre_dist.get(g, 0) + 1
        return sorted(genre_dist.items(), key=lambda x: x[1], reverse=True)

    @staticmethod
    def create(**kwargs):
        """Create new Titles record"""
        try:
            item = Titles(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e

    @staticmethod
    def update(id, **kwargs):
        """Update Titles record"""
        item = db.session.get(Titles, id)
        if not item:
            return None

        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)

        db.session.commit()
        return item

    @staticmethod
    def delete(id):
        """Delete Titles record"""
        item = db.session.get(Titles, id)
        if not item:
            return False

        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total Titles records"""
        return Titles.query.count()

    @staticmethod
    def count_up_to_date():
        """Count titles that are up to date and have base game"""
        return Titles.query.filter(Titles.up_to_date == True, Titles.have_base == True).count()

    @staticmethod
    def get_owned_ids_from_list(title_ids):
        """Check which TitleIDs from a list are owned (have base game)"""
        from models.apps import Apps
        from constants import APP_TYPE_BASE

        return [
            row[0]
            for row in db.session.query(Titles.title_id)
            .join(Apps)
            .filter(Titles.title_id.in_(title_ids), Apps.app_type == APP_TYPE_BASE, Apps.owned == True)
            .all()
        ]
