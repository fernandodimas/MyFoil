import sys
import os
import structlog

# Ensure the current directory is in the path for Celery workers
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from celery_app import celery
from flask import Flask
from db import db, remove_missing_files_from_db
from library import scan_library_path, identify_library_files, update_titles, generate_library
from job_tracker import job_tracker, JobType
from socket_helper import get_socketio_emitter
from app_services.rating_service import update_game_metadata

import logging

# Configure structlog for Celery workers to ensure we see output
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
        if os.environ.get("LOG_FORMAT") == "json"
        else structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("main")


def create_app_context():
    """Create a minimal app context for celery tasks"""
    app = Flask(__name__)
    # We need to reach constants for DB path
    from constants import MYFOIL_DB

    app.config["SQLALCHEMY_DATABASE_URI"] = MYFOIL_DB
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    # Configure SQLite pragmas for worker process
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        import sqlite3
        if not isinstance(dbapi_connection, sqlite3.Connection):
             return

        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Initialize job tracker for worker
    from job_tracker import job_tracker
    job_tracker.init_app(app)

    try:
        with app.app_context():
            from db import log_activity
            db_type = "PostgreSQL" if "postgresql" in app.config["SQLALCHEMY_DATABASE_URI"] else "SQLite"
            log_activity("worker_startup", details={"db_type": db_type})
    except Exception as e:
        print(f"FAILED to log worker startup: {e}")

    return app


flask_app = create_app_context()

# NOTE: Emitter is configured INSIDE each task to ensure fresh connection
# This matches the pattern used by TitleDB/Backup which work correctly


@celery.task(name="tasks.scan_library_async")
def scan_library_async(library_path):
    """Full library scan in background"""
    with flask_app.app_context():
        import time
        
        # Recreate emitter fresh for THIS task execution
        logger.info("task_execution_started", task="scan_library_async", library_path=library_path)
        job_tracker.set_emitter(get_socketio_emitter())
        
        job_id = f"scan_{int(time.time())}"
        logger.info("job_tracking_started", job_id=job_id, type="LIBRARY_SCAN")
        job_tracker.start_job(job_id, JobType.LIBRARY_SCAN, f"Scanning {library_path}")

        try:
            from db import remove_missing_files_from_db
            # 1. Cleanup missing files first
            job_tracker.update_progress(job_id, 10, message="Cleaning up missing files...")
            count = remove_missing_files_from_db()
            logger.info("cleanup_completed", removed=count)

            # 2. Scan for new files
            job_tracker.update_progress(job_id, 30, message="Scanning folders...")
            scan_library_path(library_path)

            # 3. Identify new/unidentified files
            job_tracker.update_progress(job_id, 60, message="Identifying files...")
            identify_library_files(library_path)

            # 4. Update title statuses and regenerate cache
            job_tracker.update_progress(job_id, 90, message="Refreshing library...")
            update_titles()
            generate_library(force=True)

            # Notify via socketio
            from library import trigger_library_update_notification
            trigger_library_update_notification()

            job_tracker.complete_job(job_id, "Scan completed")
            logger.info("task_execution_completed", task="scan_library_async", library_path=library_path)
            return True
        except Exception as e:
            logger.exception("task_execution_failed", task="scan_library_async", error=str(e))
            job_tracker.fail_job(job_id, str(e))
            return False


@celery.task(name="tasks.identify_file_async")
def identify_file_async(filepath):
    """Identify a single file in background (e.g. from watchdog)"""
    with flask_app.app_context():
        import time
        
        # Recreate emitter fresh for THIS task execution
        job_tracker.set_emitter(get_socketio_emitter())
        
        job_id = f"id_{int(time.time())}"
        job_tracker.start_job(job_id, JobType.FILE_IDENTIFICATION, "Identifying new file")

        try:
            logger.info("background_identification_started", triggered_by=filepath)

            # For simple file changes, we can just run the global cleanup and identification
            job_tracker.update_progress(job_id, 20, message="Checking for changes...")
            from db import remove_missing_files_from_db
            remove_missing_files_from_db()

            from library import Libraries
            libraries = Libraries.query.all()
            for i, lib in enumerate(libraries):
                job_tracker.update_progress(job_id, 40 + (i*10), message=f"Identifying in {lib.path}")
                identify_library_files(lib.path)

            # Atualizar títulos e gerar biblioteca (equivalente a post_library_change)
            job_tracker.update_progress(job_id, 90, message="Refreshing library...")
            update_titles()
            generate_library(force=True)

            # Notificar via socketio
            from library import trigger_library_update_notification
            trigger_library_update_notification()

            job_tracker.complete_job(job_id, "File identification done")
            return True
        except Exception as e:
            job_tracker.fail_job(job_id, str(e))
            return False


@celery.task(name="tasks.scan_all_libraries_async")
def scan_all_libraries_async():
    """Full library scan for all configured paths in background"""
    with flask_app.app_context():
        import time

        # Recreate emitter fresh for THIS task execution
        logger.info("task_execution_started", task="scan_all_libraries_async")
        job_tracker.set_emitter(get_socketio_emitter())

        job_id = f"scan_all_{int(time.time())}"
        logger.info("job_tracking_started", job_id=job_id, type="LIBRARY_SCAN")
        job_tracker.start_job(job_id, JobType.LIBRARY_SCAN, "Scanning all libraries")

        try:
            from db import remove_missing_files_from_db, get_libraries
            job_tracker.update_progress(job_id, 10, message="Cleaning up missing files...")
            count = remove_missing_files_from_db()
            logger.info("cleanup_completed", removed=count)

            libraries = get_libraries()
            total = len(libraries)
            for i, lib in enumerate(libraries):
                msg = f"Scanning {lib.path}"
                job_tracker.update_progress(job_id, 20 + int((i/total)*60), message=msg)
                logger.info("scanning_path", path=lib.path)
                scan_library_path(lib.path)
                identify_library_files(lib.path)

            # Atualizar títulos e gerar biblioteca
            job_tracker.update_progress(job_id, 90, message="Refreshing library...")
            update_titles()
            generate_library(force=True)

            # Notificar via socketio
            from library import trigger_library_update_notification
            trigger_library_update_notification()

            job_tracker.complete_job(job_id, "Full scan completed")
            logger.info("task_execution_completed", task="scan_all_libraries_async")
            return True
        except Exception as e:
            logger.exception("task_execution_failed", task="scan_all_libraries_async", error=str(e))
            job_tracker.fail_job(job_id, str(e))
            return False


@celery.task(name="tasks.fetch_metadata_for_game_async")
def fetch_metadata_for_game_async(title_id):
    """Fetch metadata for a single game"""
    with flask_app.app_context():
        from db import Titles

        game = Titles.query.filter_by(title_id=title_id).first()
        if not game:
            logger.error("game_not_found", title_id=title_id)
            return False

        logger.info("fetching_metadata", title_id=title_id, name=game.name)
        return update_game_metadata(game, force=False)


@celery.task(name="tasks.fetch_metadata_for_all_games_async")
def fetch_metadata_for_all_games_async():
    """Background task to fetch metadata for ALL games"""
    with flask_app.app_context():
        from db import Titles
        import time

        # Recreate emitter fresh for THIS task execution
        logger.info("task_execution_started", task="fetch_metadata_for_all_games_async")
        job_tracker.set_emitter(get_socketio_emitter())

        job_id = f"metadata_{int(time.time())}"
        logger.info("job_tracking_started", job_id=job_id, type="METADATA_FETCH")
        job_tracker.start_job(job_id, JobType.METADATA_FETCH, "Fetching metadata for all games")
        
        try:
            # Only fetch for games that have at least the base game (identified)
            games = Titles.query.filter(Titles.have_base == True).all()
            total = len(games)
            logger.info("metadata_batch_started", count=total)

            if total == 0:
                job_tracker.complete_job(job_id, "No games to update")
                return True
            
            job_tracker.update_progress(job_id, 0, current=0, total=total)
            
            for i, game in enumerate(games):
                # We run synchronously here to track progress of the batch
                try:
                    update_game_metadata(game, force=False)
                except Exception as ex:
                    logger.error(f"Error updating {game.name}: {ex}")

                progress = int(((i + 1) / total) * 100)
                job_tracker.update_progress(job_id, progress, current=i+1, total=total, message=f"Updated {game.name}")

            job_tracker.complete_job(job_id, f"Finished updating {total} games")
            logger.info("task_execution_completed", task="fetch_metadata_for_all_games_async")
            return True
            
        except Exception as e:
            logger.exception("task_execution_failed", task="fetch_metadata_for_all_games_async", error=str(e))
            job_tracker.fail_job(job_id, str(e))
            return False

@celery.task(name="tasks.update_titledb_async")
def update_titledb_async(force=False):
    """Update TitleDB in background"""
    with flask_app.app_context():
        from titledb import update_titledb
        from settings import load_settings
        
        logger.info("task_execution_started", task="update_titledb_async")
        
        # Reload settings to ensure we have the latest (e.g. new sources)
        settings = load_settings()
        
        return update_titledb(settings, force=force)
