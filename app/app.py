"""
MyFoil - Enhanced Nintendo Switch Library Manager
Application Factory e Inicialização
# Force rebuild for import fix
"""

from gevent import monkey

monkey.patch_all()

import os
import sys
import logging

import flask.cli

flask.cli.show_server_banner = lambda *args: None

# Silence noisy libraries
logging.getLogger("engineio.server").setLevel(logging.CRITICAL)
logging.getLogger("socketio.server").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
logging.getLogger("geventwebsocket.handler").setLevel(logging.WARNING)
logging.getLogger("geventwebsocket.server").setLevel(logging.WARNING)

# Core Flask imports
from flask import Flask, render_template, Blueprint
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Local imports
from constants import (
    MYFOIL_DB,
    BUILD_VERSION,
    CONFIG_DIR,
    PLUGINS_DIR,
    DATA_DIR,
)
from settings import load_settings, reload_conf
from db import db
import db as db_module
from i18n import I18n
import titles
import titledb

from rest_api import init_rest_api
import structlog
from metrics import init_metrics
from backup import BackupManager
from plugin_system import get_plugin_manager

# Routes and services

from routes.library import library_bp
from routes.settings import settings_bp
from routes.system import system_bp, system_web_bp
from routes.web import web_bp
from routes.wishlist import wishlist_bp
from routes.upcoming import upcoming_bp

# Jobs
from scheduler import init_scheduler

# Optional Celery for async tasks
try:
    from celery_app import celery  # noqa: F401
    from tasks import fetch_metadata_for_all_games_async

    # Test Redis connection before enabling Celery
    import redis

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    r = redis.from_url(redis_url)
    try:
        r.ping()
        CELERY_ENABLED = True
        logging.info("Redis connection established - Async background tasks enabled (Celery)")
    except Exception as redis_error:
        # Check if environment expects Redis
        if os.environ.get("CELERY_REQUIRED", "false").lower() == "true":
            logging.error(f"Redis required but not reachable: {redis_error}")
            CELERY_ENABLED = False
        else:
            logging.info("Redis not available - Async background tasks disabled (Celery)")
            CELERY_ENABLED = False
except ImportError:
    CELERY_ENABLED = False

# Import additional modules for functions
from auth import access_required, auth_blueprint, login_manager, init_users
from db import User, log_activity, init_db, delete_file_by_filepath, file_exists_in_db, update_file_path
from library import (
    scan_library_path,
    identify_library_files,
    add_missing_apps_to_db,
    update_titles,
    init_libraries,
    invalidate_library_cache,
    add_files_to_library,
    post_library_change,
)
from utils import now_utc, ColoredFormatter, FilterRemoveDateFromWerkzeugLogs, get_or_create_secret_key
import library as library_mod
from file_watcher import Watcher
import threading
import time
from datetime import timedelta

from app_factory import socketio, limiter, app_settings

# Import state to allow job tracking
import state
from job_tracker import job_tracker
from socket_helper import get_socketio_emitter

job_tracker.set_emitter(get_socketio_emitter())

backup_manager = None
plugin_manager = None


# Logging configuration
formatter = ColoredFormatter(
    "[%(asctime)s.%(msecs)03d] %(levelname)s (%(module)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)

# Add File Handler for persistent debug logging
ensure_data_dir = os.path.join(os.getcwd(), "data")
if not os.path.exists(ensure_data_dir):
    try:
        os.makedirs(ensure_data_dir)
    except OSError:
        pass

log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper())

handlers = [handler]
try:
    file_handler = logging.FileHandler(os.path.join(ensure_data_dir, "debug.log"))
    file_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s (%(module)s) %(message)s"))
    file_handler.setLevel(log_level)
    handlers.append(file_handler)
except PermissionError:
    pass  # Volume may have root-owned files from previous container

logging.basicConfig(level=log_level, handlers=handlers)

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

# Apply filter to hide date from http access logs
logging.getLogger("werkzeug").addFilter(FilterRemoveDateFromWerkzeugLogs())
logging.getLogger("alembic.runtime.migration").setLevel(logging.WARNING)



@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login"""
    return db.session.get(User, int(user_id))






def update_titledb_job(force=False):
    """Update TitleDB in background"""
    with app.app_context():
        job_tracker.set_emitter(get_socketio_emitter())

        # Track job
        job_id = job_tracker.register_job("titledb_update", {"force": force})
        job_tracker.start_job(job_id)

        with state.titledb_update_lock:
            if state.is_titledb_update_running:
                logger.info("TitleDB update already in progress.")
                job_tracker.fail_job(job_id, "Update already in progress")
                return False
            state.is_titledb_update_running = True

        logger.info("Starting TitleDB update job...")
        try:
            job_tracker.update_progress(job_id, 0, 10, "Initializing...")
            time.sleep(0.1)

            job_tracker.update_progress(job_id, 1, 10, "Downloading TitleDB files...")
            current_settings = load_settings()

            # Step 1: Download
            # Pass job_id so update_titledb_files can report granular progress
            titledb.update_titledb_files(current_settings, force=force, job_id=job_id)

            # Step 2: Reload memory cache
            # Define progress callback for granular updates
            def progress_cb(msg, percent):
                # Map load_titledb progress (0-100) to job progress (1-4)
                # This is just for the loading phase
                scaled_progress = 1 + (percent / 100 * 3)
                job_tracker.update_progress(job_id, int(scaled_progress), 10, msg)
                try:
                    import gevent

                    gevent.sleep(0)
                except Exception:
                    pass

            # Step 2: Reload memory cache
            # titles.load_titledb will call progress_cb
            titles.load_titledb(force=True, progress_callback=progress_cb)

            # Step 3: Sync to database metadata (PostgreSQL)
            job_tracker.update_progress(job_id, 5, 10, "Syncing database metadata...")
            add_missing_apps_to_db()
            update_titles()

            # Step 4: Optional Library identification
            # We only do this if specifically needed, or we do it faster

            # Instead of full identification of every file (which is slow),
            # we just invalidate the cache so new titles appear,
            # and let the user trigger a scan if they want a full refresh.
            job_tracker.update_progress(job_id, 8, 10, "Refreshing library views...")
            invalidate_library_cache()
            # generate_library(force=True)  <-- REMOVED: Too slow and blocking

            job_tracker.update_progress(job_id, 10, 10, "Finalizing...")
            logger.info("TitleDB update completed and library views refreshed.")

            job_tracker.complete_job(job_id, {"success": True})
            return True
        except Exception as e:
            logger.error(f"Error during TitleDB update job: {e}")
            try:
                log_activity("titledb_update_failed", details={"error": str(e)})
            except Exception:
                pass
            job_tracker.fail_job(job_id, str(e))
            return False
        finally:
            with state.titledb_update_lock:
                state.is_titledb_update_running = False


def scan_library_job():
    """Scan library in background"""
    logger.info(f"DEBUG: Entering scan_library_job (BUILD: {BUILD_VERSION})")
    with app.app_context():
        # Track job
        job_id = job_tracker.register_job("aggregate_scan")
        job_tracker.start_job(job_id)

        with state.titledb_update_lock:
            if state.is_titledb_update_running:
                # Double check with job_tracker if there is REALLY a job running
                active_jobs = job_tracker.get_active_jobs()
                active_titledb_jobs = [j for j in active_jobs if j.get("type") == "titledb_update"]

                if not active_titledb_jobs:
                    logger.warning(
                        "state.is_titledb_update_running was True but no active job found in DB. Resetting flag."
                    )
                    state.is_titledb_update_running = False
                else:
                    logger.info(
                        f"Skipping library scan: TitleDB update job {active_titledb_jobs[0]['id']} is in progress."
                    )
                    job_tracker.fail_job(job_id, "TitleDB update in progress")
                    return

        logger.info(f"Starting library scan job (Job ID: {job_id})")

        # Check if there are already other active scan jobs
        active_jobs = job_tracker.get_active_jobs()
        active_scan_jobs = [
            j
            for j in active_jobs
            if j.get("type") in ["library_scan", "aggregate_scan", "file_identification"] and j.get("id") != job_id
        ]

        if active_scan_jobs:
            logger.warning(
                f"Skipping library scan: {len(active_scan_jobs)} other scan job(s) already in progress ({[j['id'] for j in active_scan_jobs]})."
            )
            job_tracker.fail_job(job_id, f"{len(active_scan_jobs)} scan job(s) already running")
            return

        with state.scan_lock:
            if state.scan_in_progress:
                logger.info("Skipping library scan: scan already in progress.")
                job_tracker.fail_job(job_id, "Scan already in progress")
                return
            state.scan_in_progress = True
        try:
            from metrics import ACTIVE_SCANS

            with ACTIVE_SCANS.track_inprogress():
                if CELERY_ENABLED:
                    from tasks import scan_all_libraries_async

                    scan_all_libraries_async.delay()
                    logger.info("Scheduled library scan queued to Celery.")
                    log_activity("library_scan_queued", details={"source": "scheduler"})
                    job_tracker.update_progress(job_id, 100, message="Scan task queued to Celery.")
                else:
                    libraries = db_module.get_libraries()
                    logger.info(f"Found {len(libraries)} libraries to scan")
                    for i, lib in enumerate(libraries):
                        try:
                            job_tracker.update_progress(job_id, i + 1, len(libraries), f"Scanning {lib.path}...")
                            logger.info(f"Scanning library: {lib.path}")
                            scan_library_path(lib.path)

                            job_tracker.update_progress(
                                job_id, i + 1, len(libraries), f"Identifying files in {lib.path}..."
                            )
                            logger.info(f"Scan complete for {lib.path}, starting identification")
                            identify_library_files(lib.path)
                            logger.info(f"Identification complete for {lib.path}")
                        except Exception as lib_err:
                            logger.error(f"Error scanning library {lib.path}: {lib_err}")
                            continue

                # No need to call post_library_change here as scan_library_path now does it
            log_activity("library_scan_completed")
            logger.info("Library scan job completed successfully.")
            job_tracker.complete_job(job_id, {"total_libraries": len(db_module.get_libraries())})
        except Exception as e:
            logger.error(f"Error during library scan job: {e}")
            log_activity("library_scan_failed", details={"error": str(e)})
            job_tracker.fail_job(job_id, str(e))
        finally:
            with state.scan_lock:
                state.scan_in_progress = False


def create_automatic_backup():
    """Create automatic backup"""
    from app_factory import backup_manager
    if backup_manager:
        logger.info("Starting automatic backup...")
        success, timestamp = backup_manager.create_backup()
        if success:
            logger.info(f"Automatic backup completed: {timestamp}")
        else:
            logger.error("Automatic backup failed")


def incremental_library_update_job():
    """Incremental library update job (Phase 3.2)"""
    logger.info("Starting incremental library update job...")
    with app.app_context():
        job_id = job_tracker.register_job("incremental_library_update")
        job_tracker.start_job(job_id)

        try:
            from library import incremental_library_update

            incremental_library_update()
            job_tracker.complete_job(job_id)
            logger.info("Incremental library update job completed successfully")
        except Exception as e:
            logger.error(f"Incremental library update job failed: {e}")
            job_tracker.fail_job(job_id, str(e))


from app_factory import create_app

# Create app instance
app = create_app()

if __name__ == "__main__":
    logger.info(f"Build Version: {BUILD_VERSION}")
    logger.info("Starting server on port 8465...")
    socketio.run(app, debug=True, use_reloader=False, host="0.0.0.0", port=8465, allow_unsafe_werkzeug=True)
    logger.info("Shutting down server...")
