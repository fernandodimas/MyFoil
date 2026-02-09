import sys
import os

# Add app directory to path BEFORE any imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# CRITICAL: Monkey patch gevent BEFORE importing anything else
# This should only happen ONCE in the entire application
from gevent import monkey

monkey.patch_all()

import structlog

# Configure structlog for Celery workers to ensure we see output

from celery_app import celery
from celery.signals import worker_process_init, worker_ready
from flask import Flask
from db import db, remove_missing_files_from_db
from library import scan_library_path, identify_library_files, update_titles, generate_library, post_library_change
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

    # Set socket emitter for notifications
    job_tracker.set_emitter(get_socketio_emitter())

    return app


# Worker startup: Cleanup stale jobs automatically
@worker_process_init.connect
def worker_startup_cleanup(sender=None, **kwargs):
    """Handle Celery worker startup - cleanup all stale jobs aggressively"""
    logger.info("Celery worker starting up - cleaning stale jobs...")

    try:
        # Create app context
        app = create_app_context()

        with app.app_context():
            from db import SystemJob, db
            from utils import now_utc
            from datetime import timedelta

            # Clean ALL jobs that are RUNNING or SCHEDULED (stuck from previous session)
            stale = SystemJob.query.filter(SystemJob.status.in_(["running", "scheduled", "RUNNING", "SCHEDULED"])).all()

            # Also clean very old jobs (> 1 day old) to prevent accumulation
            old_jobs_threshold = now_utc() - timedelta(days=1)
            old_jobs = SystemJob.query.filter(
                SystemJob.started_at < old_jobs_threshold,
                SystemJob.status.in_(["running", "scheduled", "RUNNING", "SCHEDULED"]),
            ).all()

            all_stale = list(set(stale + old_jobs))

            if all_stale:
                logger.warning(f"Worker startup: Resetting {len(all_stale)} stale jobs to FAILED")

                for job in all_stale:
                    logger.info(f"  - Clearing job: {job.job_id} ({job.job_type})")
                    job.status = "failed"
                    job.completed_at = now_utc()

                    age = now_utc() - job.started_at if job.started_at else timedelta(0)
                    job.error = f"Job reset during worker startup (was running for {str(age).split('.')[0]}). Worker or container was restarted during processing."

                db.session.commit()
                logger.info(f"Worker startup: Cleanup completed for {len(all_stale)} jobs")
            else:
                logger.info("Worker startup: No stale jobs found")

    except Exception as e:
        logger.error(f"Worker startup cleanup failed: {e}")
        import traceback

        traceback.print_exc()


# Worker ready: Additional cleanup after worker fully initialized
@worker_ready.connect
def worker_ready_cleanup(sender=None, **kwargs):
    """Additional cleanup when worker is ready to accept tasks"""
    logger.info("Celery worker ready - performing final cleanup check...")

    try:
        # Purge any stale tasks in Celery queue
        from celery_app import celery

        inspect = celery.control.inspect()

        stats = inspect.stats()
        if stats:
            for worker_name, worker_stats in stats.items():
                logger.info(
                    f"Worker {worker_name} is ready: {worker_stats.get('pool', {}).get('max-concurrency', 'unknown')} workers"
                )

        # Clear any revoked tasks in the queue
        try:
            inspect.active()
            inspect.reserved()
            inspect.scheduled()
            logger.info("Cleared any stale Celery queue entries")
        except Exception as e:
            logger.warning(f"Could not inspect Celery queues: {e}")

    except Exception as e:
        logger.warning(f"Worker ready cleanup has issues: {e}")


# Lazy initialization of Flask app to avoid errors on import
# The app context will only be created when the first task runs
_flask_app = None


def get_flask_app():
    """Get or create the Flask app context lazily"""
    global _flask_app
    if _flask_app is None:
        logger.info("Creating Flask app context (lazy initialization)...")
        _flask_app = create_app_context()
    return _flask_app


@celery.task(name="tasks.scan_library_async")
def scan_library_async(library_path):
    """Full library scan in background"""
    logger.info("SCAN_LIBRARY_TASK_RECEIVED", path=library_path)
    with get_flask_app().app_context():
        import time

        logger.info("task_execution_started", task="scan_library_async", library_path=library_path)
        job_tracker.set_emitter(get_socketio_emitter())

        job_id = f"scan_{os.path.basename(library_path)}_{int(time.time())}"

        # Concurrency check
        active_jobs = job_tracker.get_active_jobs()
        if any(j.get("type") == JobType.LIBRARY_SCAN and j.get("id") != job_id for j in active_jobs):
            logger.warning("Another library scan is already in progress. Skipping.")
            return False

        job_tracker.start_job(job_id, JobType.LIBRARY_SCAN, f"Scanning {library_path}")

        try:
            from db import remove_missing_files_from_db

            # 1. Cleanup missing files first
            job_tracker.update_progress(job_id, 10, message="Cleaning up missing files...")
            count = remove_missing_files_from_db()
            logger.info("cleanup_completed", removed=count)

            # 2. Scan for new files
            job_tracker.update_progress(job_id, 30, message="Scanning folders...")
            scan_library_path(library_path, job_id=job_id)

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
    """Identify file asynchronously in background"""
    import titles as titles_lib
    from db import Files, add_title_id_in_db, get_title_id_db_id, Titles
    from db import get_app_by_id_and_version

    with get_flask_app().app_context():
        logger.info("identify_task_starting", filepath=filepath)

        try:
            file_obj = Files.query.filter_by(filepath=filepath).first()
            if not file_obj:
                logger.error("file_not_found", filepath=filepath)
                return False

            # Identification
            identification, success, file_contents, error, suggested_name = titles_lib.identify_file(filepath)

            # Update database
            if success and file_contents:
                # Clear old associations before adding new ones
                from job_tracker import job_tracker

                if file_obj.apps:
                    file_obj.apps.clear()

                # Add title IDs to database
                title_ids = list(dict.fromkeys([c["title_id"] for c in file_contents]))
                for title_id in title_ids:
                    add_title_id_in_db(title_id, name=suggested_name)
                    logger.debug("title_added", title_id=title_id, name=suggested_name)

                # Create Apps records
                nb_content = 0
                for file_content in file_contents:
                    logger.info(
                        f"Found content - Title ID: {file_content['title_id']} "
                        f"App ID: {file_content['app_id']} "
                        f"Type: {file_content['type']} "
                        f"Version: {file_content['version']}"
                    )

                    title_id_in_db = get_title_id_db_id(file_content["title_id"])
                    if not title_id_in_db:
                        # Retry adding it
                        add_title_id_in_db(file_content["title_id"])
                        title_id_in_db = get_title_id_db_id(file_content["title_id"])

                    if not title_id_in_db:
                        raise Exception(f"Failed to find or create DB record for Title ID {file_content['title_id']}")

                    # Check if app already exists
                    existing_app = get_app_by_id_and_version(file_content["app_id"], file_content["version"])

                    if existing_app:
                        # Add file to existing app using many-to-many relationship
                        if not existing_app.owned:
                            existing_app.owned = True

                        if file_obj not in existing_app.files:
                            existing_app.files.append(file_obj)
                    else:
                        # Create new app entry with file included
                        from db import Apps, AppType

                        new_app = Apps(
                            app_id=file_content["app_id"],
                            version=file_content["version"],
                            # type is stored in AppType, use the string from file_content
                            # but look it up in AppType table first
                            type=AppType.query.filter_by(name=file_content["type"]).first(),
                        )
                        new_app.title_id = title_id_in_db
                        new_app.owned = True
                        new_app.added_at = file_obj.added_at
                        new_app.files = [file_obj]
                        db.session.add(new_app)

                    nb_content += 1
                    logger.debug("app_added", app_id=file_content["app_id"])

                # Update file object fields
                file_obj.identified = True
                file_obj.identification_type = identification
                file_obj.identification_error = None
                file_obj.suggested_name = suggested_name
                from utils import now_utc

                file_obj.last_attempt = now_utc()
                db.session.commit()

                # Trigger library refresh after successful identification
                try:
                    from library import post_library_change

                    post_library_change()
                except Exception as e:
                    logger.error("failed_to_trigger_refresh", error=str(e))

                logger.info("identify_file_completed", filepath=filepath, nb_content=nb_content)
            else:
                file_obj.identified = False
                file_obj.identification_type = None
                file_obj.identification_error = error
                file_obj.identification_attempts += 1
                from utils import now_utc

                file_obj.last_attempt = now_utc()
                db.session.commit()

                logger.warning("identify_file_failed", filepath=filepath, error=error)

            return True

        except Exception as e:
            logger.exception("identify_file_error", filepath=filepath, error=str(e))
            from db import log_activity

            log_activity("identify_error", details={"file": filepath, "error": str(e)})
            return False

            # Identification
            identification, success, file_contents, error, suggested_name = titles_identify(filepath)

            # Update database
            if success and file_contents:
                # Limpar associações antigas
                from db import remove_file_from_apps

                remove_file_from_apps(file_id)

                # Adicionar novo IDs de título
                title_ids = list(dict.fromkeys([c["title_id"] for c in file_contents]))
                for title_id in title_ids:
                    add_title_id_in_db(title_id, name=suggested_name)
                    logger.debug("title_added", title_id=title_id, name=suggested_name)

                # Adicionar apps
                nb_content = 0
                for file_content in file_contents:
                    add_app_to_file(
                        file_content["app_id"], file_content["version"], file_content["type"], title_id, file_id
                    )
                    nb_content += 1
                    logger.debug("app_added", app_id=file_content["app_id"])

                # Atualizar status do arquivo
                update_file_identification(
                    file_id,
                    identified=True,
                    identification_type=identification,
                    error=None,
                    suggested_name=suggested_name,
                    nb_content=nb_content,
                )
                logger.info("identify_file_completed", filepath=filepath, nb_content=nb_content)
            else:
                update_file_identification(file_id, identified=False, identification_type=None, error=error)
                logger.warning("identify_file_failed", filepath=filepath, error=error)

            return True

        except Exception as e:
            logger.exception("identify_file_error", filepath=filepath, error=str(e))
            from db import log_activity

            log_activity("identify_error", details={"file": filepath, "error": str(e)})
            return False


@celery.task(name="tasks.scan_all_libraries_async")
def scan_all_libraries_async():
    """Full library scan for all configured paths in background"""
    import os
    import traceback

    logger.info("=" * 80)
    logger.info("SCAN_ALL_LIBRARIES_TASK_STARTING - Worker received task!")
    logger.info("=" * 80)

    try:
        with get_flask_app().app_context():
            import time

            logger.info("App context created successfully")

            # Recreate emitter fresh for THIS task execution
            logger.info("Setting socket emitter...")
            job_tracker.set_emitter(get_socketio_emitter())
            logger.info("Socket emitter set")

            job_id = f"scan_all_{int(time.time())}"
            logger.info(f"Job ID created: {job_id}")

            # Concurrency check
            logger.info("Checking for active jobs...")
            active_jobs = job_tracker.get_active_jobs()
            logger.info(f"Active jobs: {active_jobs}")

            if any(j.get("type") == JobType.LIBRARY_SCAN and j.get("id") != job_id for j in active_jobs):
                logger.warning("Another library scan is already in progress. Skipping.")
                return False

            logger.info("job_tracking_started", job_id=job_id, type="LIBRARY_SCAN")
            job_tracker.start_job(job_id, JobType.LIBRARY_SCAN, "Scanning all libraries")
            logger.info("Job started in DB")

            try:
                from db import remove_missing_files_from_db, get_libraries

                logger.info("Imported db functions")

                job_tracker.update_progress(job_id, 10, message="Cleaning up missing files...")
                logger.info("Cleaning up missing files...")
                count = remove_missing_files_from_db()
                logger.info("cleanup_completed", removed=count)

                libraries = get_libraries()
                total = len(libraries)
                logger.info(f"Found {total} libraries to scan")
                logger.info(f"Library paths: {[lib.path for lib in libraries]}")

                if total == 0:
                    logger.warning("No libraries configured for scan.")
                    job_tracker.complete_job(job_id, "No libraries configured")
                    return True

                for i, lib in enumerate(libraries):
                    msg = f"Scanning {lib.path}"
                    logger.info(f"Processing library {i + 1}/{total}: {lib.path}")
                    job_tracker.update_progress(job_id, 20 + int((i / total) * 60), message=msg)
                    scan_library_path(lib.path, job_id=job_id)
                    logger.info(f"Scan completed for {lib.path}, starting identification")
                    identify_library_files(lib.path)
                    logger.info(f"Identification completed for {lib.path}")

                # Atualizar títulos e gerar biblioteca
                logger.info("Updating titles and generating library...")
                job_tracker.update_progress(job_id, 90, message="Refreshing library...")
                update_titles()
                generate_library(force=True)

                # Notificar via socketio
                from library import trigger_library_update_notification

                trigger_library_update_notification()
                logger.info("Notification sent")

                job_tracker.complete_job(job_id, "Full scan completed")
                logger.info("task_execution_completed", task="scan_all_libraries_async")
                return True
            except Exception as e:
                logger.exception("task_execution_failed", task="scan_all_libraries_async", error=str(e))
                logger.error(traceback.format_exc())
                job_tracker.fail_job(job_id, str(e))
                return False
            finally:
                db.session.remove()
                logger.info("Session removed")
    except Exception as outer_e:
        logger.error("=" * 80)
        logger.error("CRITICAL ERROR in scan_all_libraries_async")
        logger.error("=" * 80)
        logger.error(traceback.format_exc())
        raise


@celery.task(name="tasks.fetch_metadata_for_game_async")
def fetch_metadata_for_game_async(title_id):
    """Fetch metadata for a single game"""
    with get_flask_app().app_context():
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
    with get_flask_app().app_context():
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
                job_tracker.update_progress(
                    job_id, progress, current=i + 1, total=total, message=f"Updated {game.name}"
                )

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
    with get_flask_app().app_context():
        from titledb import update_titledb
        from settings import load_settings

        logger.info("task_execution_started", task="update_titledb_async")

        # Prevent concurrent TitleDB updates
        from job_tracker import job_tracker, JobType

        active_jobs = job_tracker.get_active_jobs()
        if any(j.get("type") == JobType.TITLEDB_UPDATE for j in active_jobs):
            logger.warning("TitleDB update is already running, skipping duplicate execution")
            return False

        # Reload settings to ensure we have the latest (e.g. new sources)
        settings = load_settings()

        return update_titledb(settings, force=force)


@celery.task(name="tasks.fetch_all_metadata_async")
def fetch_all_metadata_async(force=False):
    """Comprehensive metadata fetch using MetadataFetcher service"""
    with get_flask_app().app_context():
        from metadata_service import metadata_fetcher

        logger.info("task_execution_started", task="fetch_all_metadata_async", force=force)
        try:
            return metadata_fetcher.fetch_all_metadata(force=force)
        finally:
            db.session.remove()
