from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.dialects.sqlite import insert  # Use postgresql if using PostgreSQL
from flask_migrate import Migrate, upgrade
from alembic.runtime.migration import MigrationContext
from alembic.config import Config
from alembic.script import ScriptDirectory
from flask_login import UserMixin
from alembic import command
import os
import sys
import shutil
import logging
import datetime
from constants import *

# Retrieve main logger
logger = logging.getLogger("main")

db = SQLAlchemy()
migrate = Migrate()


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


def create_db_backup():
    current_revision = get_current_db_version()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f".backup_v{current_revision}_{timestamp}.db"
    backup_path = os.path.join(CONFIG_DIR, backup_filename)
    shutil.copy2(DB_FILE, backup_path)
    logger.info(f"Database backup created: {backup_path}")


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


class Libraries(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String, unique=True, nullable=False)
    last_scan = db.Column(db.DateTime)


class Files(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    library_id = db.Column(db.Integer, db.ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False)
    filepath = db.Column(db.String, unique=True, nullable=False)
    folder = db.Column(db.String)
    filename = db.Column(db.String, nullable=False)
    extension = db.Column(db.String)
    size = db.Column(db.Integer)
    compressed = db.Column(db.Boolean, default=False)
    multicontent = db.Column(db.Boolean, default=False)
    nb_content = db.Column(db.Integer, default=0)
    download_count = db.Column(db.Integer, default=0)
    identified = db.Column(db.Boolean, default=False)
    identification_type = db.Column(db.String)
    identification_error = db.Column(db.String)
    identification_attempts = db.Column(db.Integer, default=0)
    last_attempt = db.Column(db.DateTime, default=datetime.datetime.now())
    titledb_version = db.Column(db.String)  # TitleDB version when file was identified

    library = db.relationship("Libraries", backref=db.backref("files", lazy=True, cascade="all, delete-orphan"))

    __table_args__ = (
        # Composite index for library_id + identified queries (used in stats)
        db.Index("idx_files_library_identified", "library_id", "identified"),
        # Index for filepath lookups (helps with joins and lookups)
        db.Index("ix_files_filepath", "filepath"),
    )


class Titles(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title_id = db.Column(db.String, unique=True, index=True)  # Index for faster lookups
    have_base = db.Column(db.Boolean, default=False)
    up_to_date = db.Column(db.Boolean, default=False)
    complete = db.Column(db.Boolean, default=False)

    # Metadata fields (Previously stored in JSON cache)
    name = db.Column(db.String)
    icon_url = db.Column(db.String)
    banner_url = db.Column(db.String)
    category = db.Column(db.String)  # Comma separated or JSON string
    release_date = db.Column(db.String)
    publisher = db.Column(db.String)
    description = db.Column(db.Text)
    size = db.Column(db.BigInteger)
    nsuid = db.Column(db.String)

    # Track when it was last updated from TitleDB vs User edit
    last_updated = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())
    is_custom = db.Column(db.Boolean, default=False)  # True if edited by user
    added_at = db.Column(db.DateTime)  # When game was first added to library

    tags = db.relationship("Tag", secondary="title_tag", backref=db.backref("titles", lazy="dynamic"))


# TitleDB Cache - stores downloaded TitleDB data for fast access
class TitleDBCache(db.Model):
    __tablename__ = "titledb_cache"

    id = db.Column(db.Integer, primary_key=True)
    title_id = db.Column(db.String(16), unique=True, nullable=False, index=True)
    data = db.Column(db.JSON, nullable=False)  # Full title data as JSON
    source = db.Column(db.String(50), nullable=False)  # 'titles.json', 'titles.BR.pt.json', etc.
    downloaded_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, default=db.func.now(), onupdate=db.func.now())

    # Indexes for fast lookups
    __table_args__ = (db.Index("idx_source", "source"),)


class TitleDBVersions(db.Model):
    __tablename__ = "titledb_versions"

    id = db.Column(db.Integer, primary_key=True)
    title_id = db.Column(db.String(16), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    release_date = db.Column(db.String(8))  # YYYYMMDD

    __table_args__ = (db.Index("idx_title_version", "title_id", "version"),)


class TitleDBDLCs(db.Model):
    __tablename__ = "titledb_dlcs"

    id = db.Column(db.Integer, primary_key=True)
    base_title_id = db.Column(db.String(16), nullable=False, index=True)
    dlc_app_id = db.Column(db.String(16), nullable=False, index=True)

    __table_args__ = (
        db.Index("idx_dlc_base", "base_title_id"),
        db.Index("idx_dlc_app", "dlc_app_id"),
    )


# Association table for many-to-many relationship between Apps and Files
app_files = db.Table(
    "app_files",
    db.Column("app_id", db.Integer, db.ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True),
    db.Column("file_id", db.Integer, db.ForeignKey("files.id", ondelete="CASCADE"), primary_key=True),
)


class Apps(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title_id = db.Column(db.Integer, db.ForeignKey("titles.id", ondelete="CASCADE"), nullable=False)
    app_id = db.Column(db.String, index=True)  # Index for faster lookups
    app_version = db.Column(db.String)
    app_type = db.Column(db.String, index=True)  # Index for filtering by type
    owned = db.Column(db.Boolean, default=False, index=True)  # Index for owned filter

    title = db.relationship("Titles", backref=db.backref("apps", lazy=True, cascade="all, delete-orphan"))
    files = db.relationship("Files", secondary=app_files, backref=db.backref("apps", lazy="select"))

    __table_args__ = (
        db.UniqueConstraint("app_id", "app_version", name="uq_apps_app_version"),
        # Composite index for common query patterns
        db.Index("idx_app_id_version", "app_id", "app_version"),
        db.Index("idx_owned_type", "owned", "app_type"),
        db.Index("idx_title_type", "title_id", "app_type"),
    )


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    admin_access = db.Column(db.Boolean)
    shop_access = db.Column(db.Boolean)
    backup_access = db.Column(db.Boolean)

    @property
    def is_admin(self):
        return self.admin_access

    def has_shop_access(self):
        return self.shop_access

    def has_backup_access(self):
        return self.backup_access

    def has_admin_access(self):
        return self.admin_access

    def has_access(self, access):
        if access == "admin":
            return self.has_admin_access()
        elif access == "shop":
            return self.has_shop_access()
        elif access == "backup":
            return self.has_backup_access()


class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(7))  # Hex color
    icon = db.Column(db.String(50))  # Bootstrap/FontAwesome icon class


class TitleTag(db.Model):
    title_id = db.Column(db.String, db.ForeignKey("titles.title_id", ondelete="CASCADE"), primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True)


class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"))
    title_id = db.Column(db.String, index=True)
    added_date = db.Column(db.DateTime, default=datetime.datetime.now)
    priority = db.Column(db.Integer, default=0)  # 0-5
    notes = db.Column(db.Text)

    # Preferências de ignored (novas colunas)
    ignore_dlc = db.Column(db.Boolean, default=False)
    ignore_update = db.Column(db.Boolean, default=False)


class WishlistIgnore(db.Model):
    """Tabela para armazenar preferências de ignore da wishlist por usuário"""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=True)
    title_id = db.Column(db.String, index=True, nullable=False)
    ignore_dlcs = db.Column(db.Text, default="{}")  # JSON: {"app_id1": true, "app_id2": false, ...}
    ignore_updates = db.Column(db.Text, default="{}")  # JSON: {"v1": true, "v2": false, ...}
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)

    __table_args__ = (db.UniqueConstraint("user_id", "title_id", name="uix_user_title_ignore"),)


class Webhook(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    events = db.Column(db.Text)  # JSON list: ['file_added', 'scan_complete']
    secret = db.Column(db.String(100))
    active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        import json

        return {
            "id": self.id,
            "url": self.url,
            "events": json.loads(self.events) if self.events else [],
            "secret": self.secret,
            "active": self.active,
        }


class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.now, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    action_type = db.Column(
        db.String(50), index=True
    )  # 'file_added', 'file_deleted', 'scan_completed', 'titledb_updated'
    title_id = db.Column(db.String, nullable=True)
    details = db.Column(db.Text)  # Stored as JSON string

    __table_args__ = (
        # Composite index for timestamp + action_type queries
        db.Index("idx_activity_timestamp_action", "timestamp", "action_type"),
    )


def log_activity(action_type, title_id=None, user_id=None, **details):
    """Utility function to log activity"""
    import json

    try:
        log = ActivityLog(user_id=user_id, action_type=action_type, title_id=title_id, details=json.dumps(details))
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")
        db.session.rollback()


def init_db(app):
    with app.app_context():
        # Ensure foreign keys are enforced when the SQLite connection is opened
        @event.listens_for(db.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

        # create or migrate database
        if "db" not in sys.argv:
            if not os.path.exists(DB_FILE):
                db.create_all()
                command.stamp(get_alembic_cfg(), "head")
                logger.info("Database created and stamped to the latest migration version.")
            else:
                # Ensure new tables are created even if DB exists
                db.create_all()

                # Proactive column check for new metadata fields (Auto-migration)
                try:
                    from sqlalchemy import text, inspect

                    engine = db.engine
                    with engine.connect() as conn:
                        inspector = inspect(engine)

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

                logger.info("Checking database migration...")
                if is_migration_needed():
                    create_db_backup()
                    upgrade()
                    logger.info("Database migration applied successfully.")

                # Backfill added_at for existing titles
                try:
                    backfill_added_at_for_existing_titles()
                except Exception as e:
                    logger.warning(f"Backfill added_at failed: {e}")


def file_exists_in_db(filepath):
    return Files.query.filter_by(filepath=filepath).first() is not None


def get_file_from_db(file_id):
    return Files.query.filter_by(id=file_id).first()


def update_file_path(library, old_path, new_path):
    try:
        # Find the file entry in the database using the old_path
        file_entry = Files.query.filter_by(filepath=old_path).one()

        # Extract the new folder and filename from the new_path
        folder = os.path.dirname(new_path)
        if os.path.normpath(library) == os.path.normpath(folder):
            # file is at the root of the library
            new_folder = ""
        else:
            new_folder = folder.replace(library, "")
            new_folder = "/" + new_folder if not new_folder.startswith("/") else new_folder

        filename = os.path.basename(new_path)

        # Update the file entry with the new path values
        file_entry.filename = filename
        file_entry.filepath = new_path
        file_entry.folder = new_folder

        # Commit the changes to the database
        db.session.commit()

        logger.info(f"File path updated successfully from {old_path} to {new_path}.")

    except NoResultFound:
        logger.warning(f"No file entry found for the path: {old_path}.")
    except Exception as e:
        db.session.rollback()  # Roll back the session in case of an error
        logger.error(f"An error occurred while updating the file path: {str(e)}")


def get_all_titles_from_db():
    results = Files.query.all()
    return [to_dict(r) for r in results]


def get_all_title_files(title_id):
    title_id = title_id.upper()
    results = Files.query.filter_by(title_id=title_id).all()
    return [to_dict(r) for r in results]


def get_all_files_with_identification(identification):
    results = Files.query.filter_by(identification_type=identification).all()
    return [to_dict(r)["filepath"] for r in results]


def get_all_files_without_identification(identification):
    results = Files.query.filter(Files.identification_type != identification).all()
    return [to_dict(r)["filepath"] for r in results]


def get_all_apps():
    apps_list = [
        {
            "id": app.id,
            "title_id": app.title.title_id if app.title else "UNKNOWN",
            "app_id": app.app_id,
            "app_version": app.app_version,
            "app_type": app.app_type,
            "owned": app.owned,
            "files_info": [{"path": f.filepath, "size": f.size} for f in app.files],
        }
        for app in Apps.query.options(db.joinedload(Apps.title), db.joinedload(Apps.files)).all()
    ]
    return apps_list


def get_all_non_identified_files_from_library(library_id):
    return Files.query.filter_by(identified=False, library_id=library_id).all()


def get_all_unidentified_files():
    """Get all files that are not identified across all libraries"""
    return Files.query.filter_by(identified=False).all()


def delete_file_from_db_and_disk(file_id):
    """Delete a file from the database and the filesystem"""
    file = db.session.get(Files, file_id)
    if not file:
        return False, "File not found in database"

    filepath = file.filepath
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Deleted file from disk: {filepath}")

        # Delete from DB (cascade should handle associations)
        db.session.delete(file)
        db.session.commit()
        return True, None
    except Exception as e:
        logger.error(f"Error deleting file {filepath}: {e}")
        return False, str(e)


def get_files_with_identification_from_library(library_id, identification_type):
    return Files.query.filter_by(library_id=library_id, identification_type=identification_type).all()


def get_filename_identified_files_needing_reidentification(library_id, current_titledb_timestamp):
    """Get files identified by 'filename' that need re-identification due to TitleDB update."""
    if current_titledb_timestamp is None:
        return []
    try:
        ts_float = float(current_titledb_timestamp)
    except (ValueError, TypeError):
        return []
    return (
        Files.query.filter(Files.library_id == library_id, Files.identification_type == "filename")
        .filter(db.or_(Files.titledb_version == None, Files.titledb_version < str(ts_float)))
        .all()
    )


def get_shop_files():
    shop_files = []
    results = Files.query.options(db.joinedload(Files.apps).joinedload(Apps.title)).all()

    for file in results:
        if file.identified:
            # Get the first app associated with this file using the many-to-many relationship
            app = file.apps[0] if file.apps else None

            if app:
                if file.multicontent or file.extension.startswith("x"):
                    title_id = app.title.title_id
                    final_filename = f"[{title_id}].{file.extension}"
                else:
                    final_filename = f"[{app.app_id}][v{app.app_version}].{file.extension}"
            else:
                final_filename = file.filename.replace(f".{file.extension}", "") + " (unidentified)." + file.extension
        else:
            final_filename = file.filename.replace(f".{file.extension}", "") + " (unidentified)." + file.extension

        shop_files.append(
            {
                "id": file.id,
                "filename": final_filename,
                "size": file.size,
                "title_id": app.title.title_id if app else None,
            }
        )

    return shop_files


def get_libraries():
    return Libraries.query.all()


def get_libraries_path():
    libraries = Libraries.query.all()
    return [l.path for l in libraries]


def add_library(library_path):
    stmt = insert(Libraries).values(path=library_path).on_conflict_do_nothing()
    db.session.execute(stmt)
    db.session.commit()


def delete_library(library):
    if not (isinstance(library, int) or library.isdigit()):
        library = get_library_id(library)

    db.session.delete(get_library(library))
    db.session.commit()


def get_library(library_id):
    return Libraries.query.filter_by(id=library_id).first()


def get_library_path(library_id):
    library_path = None
    library = Libraries.query.filter_by(id=library_id).first()
    if library:
        library_path = library.path
    return library_path


def get_library_id(library_path):
    library_id = None
    library = Libraries.query.filter_by(path=library_path).first()
    if library:
        library_id = library.id
    return library_id


def get_library_file_paths(library_id):
    return [file.filepath for file in Files.query.filter_by(library_id=library_id).all()]


def set_library_scan_time(library_id, scan_time=None):
    library = get_library(library_id)
    library.last_scan = scan_time or datetime.datetime.now()
    db.session.commit()


def get_all_titles():
    return Titles.query.all()


def get_all_titles_with_apps():
    """Get all titles with apps and files pre-loaded to avoid N+1 queries during library generation"""
    titles = Titles.query.options(joinedload(Titles.apps).joinedload(Apps.files), joinedload(Titles.tags)).all()

    results = []
    for t in titles:
        t_dict = to_dict(t)
        t_dict["apps"] = []
        for a in t.apps:
            a_dict = to_dict(a)
            # Include both for compatibility
            a_dict["files"] = [f.filepath for f in a.files]
            a_dict["files_info"] = [{"path": f.filepath, "size": f.size, "id": f.id} for f in a.files]
            t_dict["apps"].append(a_dict)
        t_dict["tags"] = [tag.name for tag in t.tags]
        results.append(t_dict)
    return results


def get_title(title_id):
    return Titles.query.filter_by(title_id=title_id).first()


def get_title_id_db_id(title_id):
    title = get_title(title_id)
    return title.id


def add_title_id_in_db(title_id):
    existing_title = Titles.query.filter_by(title_id=title_id).first()

    if not existing_title:
        new_title = Titles(title_id=title_id, added_at=datetime.datetime.now())
        db.session.add(new_title)
        db.session.commit()


def backfill_added_at_for_existing_titles():
    """Retroactively set added_at for titles that don't have it, based on earliest file date."""
    import time

    start = time.time()
    logger.info("Backfilling added_at for existing titles...")

    titles = Titles.query.all()
    updated = 0

    for title in titles:
        if not title.added_at and title.apps:
            # Find earliest file date across all apps
            earliest_date = None
            for app in title.apps:
                for file in app.files:
                    if file.last_attempt:
                        if earliest_date is None or file.last_attempt < earliest_date:
                            earliest_date = file.last_attempt
            if earliest_date:
                title.added_at = earliest_date
                updated += 1

    if updated > 0:
        db.session.commit()
        logger.info(f"Backfilled added_at for {updated} titles in {(time.time() - start):.2f}s")
    else:
        logger.info("No titles needed backfill for added_at")


def get_all_title_apps(title_id):
    title = (
        Titles.query.options(joinedload(Titles.apps).joinedload(Apps.files), joinedload(Titles.tags))
        .filter_by(title_id=title_id)
        .first()
    )
    if not title:
        return []

    results = []
    # Add tags to each app dict for convenience if needed, but title info is usually enough
    tags = [tag.name for tag in title.tags]
    for a in title.apps:
        a_dict = to_dict(a)
        a_dict["files_info"] = [{"path": f.filepath, "size": f.size, "id": f.id} for f in a.files]
        a_dict["tags"] = tags
        results.append(a_dict)
    return results


def get_app_by_id_and_version(app_id, app_version):
    """Get app entry for a specific app_id and version (unique due to constraint)"""
    return Apps.query.filter_by(app_id=app_id, app_version=app_version).first()


def get_app_files(app_id, app_version):
    """Get all file_ids associated with a specific app_id and version"""
    app = get_app_by_id_and_version(app_id, app_version)
    return [f.id for f in app.files] if app else []


def is_app_owned(app_id, app_version):
    """Check if an app is owned (has at least one file associated with it)"""
    app = get_app_by_id_and_version(app_id, app_version)
    return app.owned if app else False


def add_file_to_app(app_id, app_version, file_id):
    """Add a file to an existing app using many-to-many relationship"""
    app = get_app_by_id_and_version(app_id, app_version)
    if app:
        file_obj = get_file_from_db(file_id)
        if file_obj and file_obj not in app.files:
            app.files.append(file_obj)
            app.owned = True
            db.session.flush()  # Otimização: usar flush ao invés de commit imediato
            return True
    return False


def remove_file_from_apps(file_id):
    """Remove a file from all apps that reference it and update owned status"""
    apps_updated = 0
    file_obj = get_file_from_db(file_id)

    if file_obj:
        # Get all apps associated with this file using the many-to-many relationship
        associated_apps = file_obj.apps

        for app in associated_apps:
            # Remove the file from the app's files relationship
            app.files.remove(file_obj)

            # Update owned status based on remaining files
            app.owned = len(app.files) > 0
            apps_updated += 1

            logger.debug(f"Removed file_id {file_id} from app {app.app_id} v{app.app_version}. Owned: {app.owned}")

        if apps_updated > 0:
            db.session.flush()  # Otimização: usar flush ao invés de commit imediato

    return apps_updated


def has_owned_apps(title_id):
    """Check if a title has any owned apps"""
    title = get_title(title_id)
    if not title:
        return False

    owned_apps = Apps.query.filter_by(title_id=title.id, owned=True).first()
    return owned_apps is not None


def remove_titles_without_owned_apps():
    """Remove titles that have no owned apps - Otimizado com bulk delete"""
    titles_removed = 0
    titles = get_all_titles()

    # Otimização: Coletar IDs para bulk delete ao invés de deletar um por um
    titles_to_delete = []
    for title in titles:
        if not has_owned_apps(title.title_id):
            logger.debug(f"Removing title {title.title_id} - no owned apps remaining")
            titles_to_delete.append(title.id)
            titles_removed += 1

    # Bulk delete
    if titles_to_delete:
        Titles.query.filter(Titles.id.in_(titles_to_delete)).delete(synchronize_session=False)
        db.session.flush()  # Otimização: usar flush ao invés de commit imediato

    return titles_removed


def delete_files_by_library(library_path):
    success = True
    errors = []
    try:
        # Find all files with the given library
        files_to_delete = Files.query.filter_by(library=library_path).all()

        # Update Apps table before deleting files
        total_apps_updated = 0
        for file in files_to_delete:
            apps_updated = remove_file_from_apps(file.id)
            total_apps_updated += apps_updated

        # Delete each file
        for file in files_to_delete:
            db.session.delete(file)

        # Commit the changes
        db.session.commit()

        logger.info(f"All entries with library '{library_path}' have been deleted.")
        if total_apps_updated > 0:
            logger.info(f"Updated {total_apps_updated} app entries to remove library file references.")
        return success, errors
    except Exception as e:
        # If there's an error, rollback the session
        db.session.rollback()
        logger.error(f"An error occurred: {e}")
        success = False
        errors.append({"path": "library/paths", "error": f"An error occurred: {e}"})
        return success, errors


def delete_file_by_filepath(filepath):
    try:
        # Find file with the given filepath
        file_to_delete = Files.query.filter_by(filepath=filepath).one()
        file_id = file_to_delete.id

        # Update Apps table before deleting file
        apps_updated = remove_file_from_apps(file_id)

        # Delete file
        db.session.delete(file_to_delete)

        # Commit the changes
        db.session.commit()

        logger.info(f"File '{filepath}' removed from database.")
        if apps_updated > 0:
            logger.info(f"Updated {apps_updated} app entries to remove file reference.")

    except NoResultFound:
        logger.info(f"File '{filepath}' not present in database.")
    except Exception as e:
        # If there's an error, rollback the session
        db.session.rollback()
        logger.error(f"An error occurred while removing the file path: {str(e)}")


def remove_missing_files_from_db():
    try:
        # Query all entries in the Files table
        files = Files.query.all()

        # List to keep track of IDs to be deleted
        ids_to_delete = []

        for file_entry in files:
            # Check if the file exists on disk
            if not os.path.exists(file_entry.filepath):
                # If the file does not exist, mark this entry for deletion
                ids_to_delete.append(file_entry.id)
                logger.info(f"File not found on disk, marking for deletion: {file_entry.filepath}")

        # Update Apps table before deleting files
        total_apps_updated = 0
        if ids_to_delete:
            # Remove file_ids from Apps table and update owned status
            for file_id in ids_to_delete:
                apps_updated = remove_file_from_apps(file_id)
                total_apps_updated += apps_updated

            # Delete all marked entries from the Files table
            # use a more direct way since we already confirmed they're gone
            count = Files.query.filter(Files.id.in_(ids_to_delete)).delete(synchronize_session=False)

            db.session.commit()
            logger.info(
                f"Cleanup done: removed {count} missing files from DB, updated {total_apps_updated} app entries."
            )
        else:
            logger.debug("No missing files found to cleanup.")

    except Exception as e:
        db.session.rollback()
        logger.error(f"An error occurred while cleaning up missing files: {str(e)}")
