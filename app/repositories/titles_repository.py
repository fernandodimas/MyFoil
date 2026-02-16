"""
Repository for Titles database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

import time
import logging
from sqlalchemy import or_, func, select
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.titles import Titles
from models.apps import Apps
from repositories.wishlistignore_repository import get_flattened_ignores_for_user
from services.user_title_flags_service import upsert_user_title_flags, compute_flags_for_user_title


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
        # Use string form for joinedload to avoid static analyzer complaints
        return Titles.query.options(joinedload(Titles.apps)).all()

    @staticmethod
    def get_paged(page, per_page, sort_by="name", order="asc", query_text=None, filters=None):
        """
        Database-level pagination for titles
        """
        # Avoid eager-loading Apps by default for the paged list — loading apps for
        # every title can be expensive. Only load apps when callers explicitly
        # need them (use get_all_with_apps()).
        query = Titles.query.filter(Titles.title_id.isnot(None))

        if query_text:
            query = query.filter(
                or_(
                    Titles.name.ilike(f"%{query_text}%"),
                    Titles.publisher.ilike(f"%{query_text}%"),
                    Titles.title_id.ilike(f"%{query_text}%"),
                )
            )

        user_id = None
        if filters:
            user_id = filters.get("user_id")
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
                # DLC filter: Owned games that have missing DLCs.
                # Use the 'complete' flag which is reliably updated by update_titles().
                # The materialized counter 'missing_dlcs_count' may be stale.
                # If user-specific precomputed flags exist, prefer them for precise filtering
                if user_id:
                    # Join to user_title_flags table if available
                    utf = db.metadata.tables.get("user_title_flags")
                    if utf is not None:
                        query = query.join(utf, (utf.c.title_id == Titles.title_id) & (utf.c.user_id == user_id))
                        query = query.filter(utf.c.has_non_ignored_dlcs == True)
                    else:
                        query = query.filter(Titles.have_base == True, Titles.complete == False)
                else:
                    query = query.filter(Titles.have_base == True, Titles.complete == False)

            if filters.get("redundant"):
                # Redundant updates filter: prefer has_non_ignored_redundant flag when available.
                if user_id:
                    utf = db.metadata.tables.get("user_title_flags")
                    if utf is not None:
                        query = query.join(utf, (utf.c.title_id == Titles.title_id) & (utf.c.user_id == user_id))
                        query = query.filter(utf.c.has_non_ignored_redundant == True)
                    else:
                        # Fallback to materialized counter
                        try:
                            query = query.filter(func.coalesce(Titles.redundant_updates_count, 0) > 0)
                        except Exception:
                            count_subq = (
                                select(func.count(Apps.id))
                                .where(Apps.title_id == Titles.id, Apps.app_type == "UPD", Apps.owned == True)
                                .scalar_subquery()
                            )
                            # Note: This subquery fallback is still counting ALL updates, so it technically 
                            # needs to be > 1 to detect redundancy if the materialized column isn't there.
                            # But since we are relying on materialized count mostly, we update this to be safe or keep > 1?
                            # If DB schema is old, using > 1 is safer for "count of all updates".
                            # But we should rely on the model. 
                            # Let's assume migration passed.
                            query = query.filter(count_subq > 1)
                else:
                    try:
                        query = query.filter(func.coalesce(Titles.redundant_updates_count, 0) > 0)
                    except Exception:
                        count_subq = (
                            select(func.count(Apps.id))
                            .where(Apps.title_id == Titles.id, Apps.app_type == "UPD", Apps.owned == True)
                            .scalar_subquery()
                        )
                        query = query.filter(count_subq > 1)

        # Apply sorting
        sort_field = getattr(Titles, sort_by, Titles.name)
        if order == "desc":
            sort_field = sort_field.desc()
        query = query.order_by(sort_field)
        # Log query SQL and execution time for diagnostics
        logger = logging.getLogger("main")
        try:
            sql = str(query.statement)
        except Exception:
            sql = "<could not render SQL>"

        start = time.time()
        try:
            result = query.paginate(page=page, per_page=per_page, error_out=False)
            duration = (time.time() - start) * 1000.0
            logger.info(
                f"TitlesRepository.get_paged: sql={sql} page={page} per_page={per_page} duration_ms={duration:.1f}"
            )
            return result
        except Exception as e:
            duration = (time.time() - start) * 1000.0
            logger.error(
                f"TitlesRepository.get_paged failed: page={page} per_page={per_page} duration_ms={duration:.1f} error={e}"
            )
            raise

    @staticmethod
    def precompute_flags_for_user(user_id, limit=1000):
        """Walk recent titles and precompute per-user flags into user_title_flags table.

        This is intended to be run periodically (cron/job) or on demand after
        the user changes ignore preferences.
        """
        titles = Titles.query.limit(limit).all()
        for t in titles:
            # Build minimal apps list for compute_flags
            apps = [
                {
                    "app_id": a.app_id,
                    "app_type": a.app_type.lower(),
                    "app_version": a.app_version,
                    "owned": a.owned,
                }
                for a in t.apps
            ]
            flags = compute_flags_for_user_title(user_id, t.title_id, apps)
            try:
                upsert_user_title_flags(user_id, t.title_id, flags)
            except Exception:
                continue

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
