from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
from alembic.runtime.migration import MigrationContext
from alembic.config import Config
from alembic.script import ScriptDirectory

import sys
import logging
from constants import MYFOIL_DB, ALEMBIC_DIR, ALEMBIC_CONF
from utils import now_utc

# Retrieve main logger
logger = logging.getLogger("main")

db = SQLAlchemy()

# Ensure Webhook symbol exists for compatibility imports even if model isn't available
Webhook = None


# Alembic functions
def get_alembic_cfg():
    cfg = Config(ALEMBIC_CONF)
    cfg.set_main_option("script_location", ALEMBIC_DIR)
    return cfg


def get_current_db_version():
    engine = create_engine(MYFOIL_DB)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        current_rev = context.get_current_revision()
        return current_rev or "0"


def is_migration_needed():
    alembic_cfg = get_alembic_cfg()
    script = ScriptDirectory.from_config(alembic_cfg)
    latest_revision = script.get_current_head()
    current_revision = get_current_db_version()
    if current_revision != latest_revision:
        logger.info(f"Database migration needed, from {current_revision} to {latest_revision}")
        return True
    else:
        logger.info(f"Database version is up to date ({current_revision})")
        return False


def to_dict(db_results):
    return {c.name: getattr(db_results, c.name) for c in db_results.__table__.columns}


def log_activity(action_type, title_id=None, user_id=None, **details):
    """Utility function to log activity"""
    import json
    from flask import current_app

    try:
        # Check if we have an app context
        if not current_app or not current_app.app_context:
            logger.debug(f"Skipping log_activity (no app context): {action_type}")
            return

        log = ActivityLog(user_id=user_id, action_type=action_type, title_id=title_id, details=json.dumps(details))
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")
        try:
            db.session.rollback()
        except Exception:
            pass


def init_db(app):
    with app.app_context():
        # create or migrate database
        if "db" not in sys.argv:
            from sqlalchemy import inspect

            inspector = inspect(db.engine)
            if not inspector.has_table("files"):
                logger.info("Initializing database tables...")
                db.create_all()
                logger.info("Database schema initialized via create_all.")
            else:
                # DB exists. Ensure state is consistent.
                db.create_all()

            # Cleanup: Remove titles with null title_id
            try:
                Titles.query.filter((Titles.title_id.is_(None)) | (Titles.title_id == "")).delete()
                db.session.commit()
            except Exception as e:
                logger.warning(f"Failed to cleanup null titles: {e}")
                db.session.rollback()

            # Proactive column check for new metadata fields (Auto-migration)
            try:
                from sqlalchemy import text, inspect

                engine = db.engine
                with engine.connect() as conn:
                    inspector = inspect(engine)

                    # Check for system_jobs table
                    if not inspector.has_table("system_jobs"):
                        logger.info("Creating system_jobs table...")
                        conn.execute(
                            text("""
                            CREATE TABLE IF NOT EXISTS system_jobs (
                                job_id VARCHAR(50) NOT NULL PRIMARY KEY,
                                job_type VARCHAR(50) NOT NULL,
                                status VARCHAR(20) NOT NULL,
                                progress_percent FLOAT DEFAULT 0.0,
                                progress_message VARCHAR(255),
                                result_json JSON,
                                metadata_json JSON,
                                error TEXT,
                                started_at DATETIME,
                                completed_at DATETIME
                            )
                        """)
                        )
                        conn.commit()

                    # Check for title_metadata table
                    if not inspector.has_table("title_metadata"):
                        logger.info("Creating title_metadata table...")
                        conn.execute(
                            text("""
                            CREATE TABLE IF NOT EXISTS title_metadata (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                title_id VARCHAR(16) NOT NULL,
                                description TEXT,
                                rating FLOAT,
                                rating_count INTEGER,
                                genres JSON,
                                tags JSON,
                                release_date DATE,
                                cover_url VARCHAR(512),
                                banner_url VARCHAR(512),
                                screenshots JSON,
                                source VARCHAR(50),
                                source_id VARCHAR(100),
                                fetched_at DATETIME,
                                updated_at DATETIME
                            )
                        """)
                        )
                        conn.commit()

                    # Check titles table columns
                    existing_columns = [c["name"] for c in inspector.get_columns("titles")]
                    new_cols = [
                        ("name", "TEXT"),
                        ("icon_url", "TEXT"),
                        ("banner_url", "TEXT"),
                        ("category", "TEXT"),
                        ("release_date", "TEXT"),
                        ("publisher", "TEXT"),
                        ("description", "TEXT"),
                        ("size", "INTEGER"),
                        ("nsuid", "TEXT"),
                        ("is_custom", "BOOLEAN DEFAULT 0"),
                        ("last_updated", "DATETIME"),
                        ("added_at", "DATETIME"),
                        ("metacritic_score", "INTEGER"),
                        ("user_rating", "FLOAT"),
                        ("rawg_rating", "FLOAT"),
                        ("rating_count", "INTEGER"),
                        ("playtime_main", "INTEGER"),
                        ("playtime_extra", "INTEGER"),
                        ("playtime_completionist", "INTEGER"),
                        ("genres_json", "TEXT"),
                        ("tags_json", "TEXT"),
                        ("screenshots_json", "TEXT"),
                        ("rawg_id", "INTEGER"),
                        ("igdb_id", "INTEGER"),
                        ("api_last_update", "DATETIME"),
                        ("api_source", "VARCHAR(20)"),
                    ]

                    modified = False
                    for col_name, col_type in new_cols:
                        if col_name not in existing_columns:
                            logger.info(f"Adding missing column {col_name} to titles table...")
                            try:
                                conn.execute(text(f"ALTER TABLE titles ADD COLUMN {col_name} {col_type}"))
                                modified = True
                            except Exception as e:
                                logger.error(f"Failed to add column {col_name}: {e}")

                    if modified:
                        conn.commit()
                        logger.info("Database schema updated with new metadata columns.")

                    # Check wishlist table columns (2026-02-05)
                    wishlist_cols = [c["name"] for c in inspector.get_columns("wishlist")]
                    wishlist_extra_cols = [
                        ("name", "TEXT"),
                        ("release_date", "TEXT"),
                        ("icon_url", "TEXT"),
                        ("banner_url", "TEXT"),
                        ("description", "TEXT"),
                        ("genres", "TEXT"),
                        ("screenshots", "TEXT"),
                    ]

                    wishlist_extra_modified = False
                    for col_name, col_type in wishlist_extra_cols:
                        if col_name not in wishlist_cols:
                            logger.info(f"Adding missing column {col_name} to wishlist table...")
                            try:
                                conn.execute(text(f"ALTER TABLE wishlist ADD COLUMN {col_name} {col_type}"))
                                wishlist_extra_modified = True
                            except Exception as e:
                                logger.error(f"Failed to add column {col_name} to wishlist: {e}")

                    if wishlist_extra_modified:
                        conn.commit()
                        logger.info("Database schema updated with wishlist metadata columns.")

                    # Check wishlist table columns (2026-01-16)
                    wishlist_cols = [c["name"] for c in inspector.get_columns("wishlist")]
                    wishlist_new_cols = [
                        ("ignore_dlc", "BOOLEAN DEFAULT 0"),
                        ("ignore_update", "BOOLEAN DEFAULT 0"),
                    ]

                    wishlist_modified = False
                    for col_name, col_type in wishlist_new_cols:
                        if col_name not in wishlist_cols:
                            logger.info(f"Adding missing column {col_name} to wishlist table...")
                            try:
                                conn.execute(text(f"ALTER TABLE wishlist ADD COLUMN {col_name} {col_type}"))
                                wishlist_modified = True
                            except Exception as e:
                                logger.error(f"Failed to add column {col_name} to wishlist: {e}")

                    if wishlist_modified:
                        conn.commit()
                        logger.info("Database schema updated with wishlist ignore columns.")

                    # Create wishlist_ignore table if not exists (2026-01-16)
                    tables = inspector.get_table_names()
                    if "wishlist_ignore" not in tables:
                        logger.info("Creating wishlist_ignore table...")
                        conn.execute(
                            text("""
                            CREATE TABLE wishlist_ignore (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                user_id INTEGER,
                                title_id VARCHAR NOT NULL,
                                ignore_dlcs TEXT DEFAULT '{}',
                                ignore_updates TEXT DEFAULT '{}',
                                created_at DATETIME,
                                FOREIGN KEY (user_id) REFERENCES user (id) ON DELETE CASCADE,
                                UNIQUE (user_id, title_id)
                            )
                        """)
                        )
                        conn.commit()
                        logger.info("wishlist_ignore table created.")
                    else:
                        existing_cols = [c["name"] for c in inspector.get_columns("wishlist_ignore")]
                        if "ignore_dlc" in existing_cols and "ignore_dlcs" not in existing_cols:
                            logger.info("Migrating wishlist_ignore columns to new JSON format...")
                            try:
                                conn.execute(
                                    text("ALTER TABLE wishlist_ignore RENAME COLUMN ignore_dlc TO ignore_dlcs_old")
                                )
                                conn.execute(
                                    text(
                                        "ALTER TABLE wishlist_ignore RENAME COLUMN ignore_update TO ignore_updates_old"
                                    )
                                )
                                conn.execute(
                                    text("ALTER TABLE wishlist_ignore ADD COLUMN ignore_dlcs TEXT DEFAULT '{}'")
                                )
                                conn.execute(
                                    text("ALTER TABLE wishlist_ignore ADD COLUMN ignore_updates TEXT DEFAULT '{}'")
                                )
                                conn.commit()
                                logger.info("wishlist_ignore columns renamed and new JSON columns added.")
                            except Exception as e:
                                logger.error(f"Failed to migrate wishlist_ignore columns: {e}")

                        if "ignore_dlcs" in existing_cols:
                            conn.execute(
                                text(
                                    "UPDATE wishlist_ignore SET ignore_dlcs = '{}' WHERE ignore_dlcs IS NULL OR ignore_dlcs = ''"
                                )
                            )
                            conn.execute(
                                text(
                                    "UPDATE wishlist_ignore SET ignore_updates = '{}' WHERE ignore_updates IS NULL OR ignore_updates = ''"
                                )
                            )
                            conn.commit()
                            logger.info("Ensured ignore_dlcs and ignore_updates have default values.")

            except Exception as e:
                logger.warning(f"Auto-migration check failed: {e}")

                # Backfill added_at for existing titles
                try:
                    backfill_added_at_for_existing_titles()
                except Exception as e:
                    logger.warning(f"Backfill added_at failed: {e}")





# Import models from their new locations for backwards compatibility
# These imports are at the end to avoid circular import issues
from models.libraries import Libraries
from models.files import Files
from models.titles import Titles
from models.titledbcache import TitleDBCache
from models.titledbversions import TitleDBVersions
from models.titledbdlcs import TitleDBDLCs
from models.apps import Apps, app_files
from models.user import User
from models.apitoken import ApiToken
from models.tag import Tag
from models.titletag import TitleTag
from models.wishlist import Wishlist
from models.wishlistignore import WishlistIgnore

# Backwards-compatibility: Webhook model placeholder (introduced for removed feature)
try:
    from models.webhook import Webhook
except Exception:
    Webhook = None

# Webhook model removed
from models.titlemetadata import TitleMetadata
from models.metadatafetchlog import MetadataFetchLog
from models.systemjob import SystemJob
from models.activitylog import ActivityLog

# Legacy query functions (extracted to separate module)
from db_queries import (
    file_exists_in_db, get_file_from_db, get_file_by_filepath, update_file_path,
    get_all_titles_from_db, get_all_title_files,
    get_all_files_with_identification, get_all_files_without_identification,
    get_all_apps, get_all_non_identified_files_from_library,
    get_all_unidentified_files, delete_file_from_db_and_disk,
    get_files_with_identification_from_library,
    get_filename_identified_files_needing_reidentification,
    get_shop_files, get_libraries, get_libraries_path, add_library,
    delete_library, get_library, get_library_path, get_library_id,
    get_library_file_paths, set_library_scan_time, get_all_titles,
    get_all_titles_with_apps, get_title, get_title_id_db_id,
    add_title_id_in_db, backfill_added_at_for_existing_titles,
    get_all_title_apps, get_app_by_id_and_version, get_app_files,
    is_app_owned, add_file_to_app, remove_file_from_apps,
    has_owned_apps, remove_titles_without_owned_apps,
    delete_files_by_library, delete_file_by_filepath,
    remove_missing_files_from_db,
)

__all__ = [
    "Libraries",
    "Files",
    "Titles",
    "TitleDBCache",
    "TitleDBVersions",
    "TitleDBDLCs",
    "Apps",
    "app_files",
    "User",
    "ApiToken",
    "Tag",
    "TitleTag",
    "Wishlist",
    "WishlistIgnore",
    "Webhook",
    "TitleMetadata",
    "MetadataFetchLog",
    "SystemJob",
    "ActivityLog",
    "db",
    "file_exists_in_db", "get_file_from_db", "get_file_by_filepath", "update_file_path",
    "get_all_titles_from_db", "get_all_title_files",
    "get_all_files_with_identification", "get_all_files_without_identification",
    "get_all_apps", "get_all_non_identified_files_from_library",
    "get_all_unidentified_files", "delete_file_from_db_and_disk",
    "get_files_with_identification_from_library",
    "get_filename_identified_files_needing_reidentification",
    "get_shop_files", "get_libraries", "get_libraries_path", "add_library",
    "delete_library", "get_library", "get_library_path", "get_library_id",
    "get_library_file_paths", "set_library_scan_time", "get_all_titles",
    "get_all_titles_with_apps", "get_title", "get_title_id_db_id",
    "add_title_id_in_db", "backfill_added_at_for_existing_titles",
    "get_all_title_apps", "get_app_by_id_and_version", "get_app_files",
    "is_app_owned", "add_file_to_app", "remove_file_from_apps",
    "has_owned_apps", "remove_titles_without_owned_apps",
    "delete_files_by_library", "delete_file_by_filepath",
    "remove_missing_files_from_db",
    "now_utc",
]
