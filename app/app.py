"""
MyFoil - Enhanced Nintendo Switch Library Manager
Application Factory e Inicialização
"""

import warnings
import os
import sys
import logging

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning, module="flask_limiter")

from gevent import monkey

monkey.patch_all()

import flask.cli

flask.cli.show_server_banner = lambda *args: None

# Silence noisy libraries
logging.getLogger("engineio.server").setLevel(logging.WARNING)
logging.getLogger("socketio.server").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

# Core Flask imports
from flask import Flask
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Local imports
from constants import *
from settings import *
from db import *
from i18n import I18n
import titles
import titledb
from sqlalchemy import event
from sqlalchemy.engine import Engine
from rest_api import init_rest_api
import structlog
from metrics import init_metrics
from backup import BackupManager
from plugin_system import get_plugin_manager
from cloud_sync import get_cloud_manager

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
    from celery_app import celery
    from tasks import scan_library_async, identify_file_async, fetch_metadata_for_all_games_async

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
from db import *
from settings import *
from auth import *
from library import *
from utils import *
from file_watcher import Watcher
import threading
import datetime
from datetime import timedelta
from utils import now_utc

# Global variables
app_settings = {}

# Custom SocketIO class to gracefully handle session disconnections
# This prevents noisy 'KeyError: Session is disconnected' tracebacks in logs
class SafeSocketIO(SocketIO):
    def __call__(self, environ, start_response):
        try:
            return super().__call__(environ, start_response)
        except KeyError as e:
            if "Session is disconnected" in str(e) or "Session is closed" in str(e):
                # Return a valid 400 response instead of letting the exception bubble up to the WSGI server
                status = "400 Bad Request"
                response_headers = [("Content-type", "text/plain")]
                start_response(status, response_headers)
                return [b"Session is disconnected"]
            raise


# Initialize SocketIO with production-ready configuration
# - cors_allowed_origins="*": Allow connections from any domain (safe for this use case)
# - async_mode='gevent': Use gevent for async operations (already monkey-patched)
# - logger=False, engineio_logger=False: Disable detailed logging in production
# - ping_timeout=120, ping_interval=20: Longer timeouts and shorter intervals for stability behind proxies
# - manage_session=True: Keep Flask session integration
socketio = SafeSocketIO(
    cors_allowed_origins="*",
    async_mode="gevent",
    logger=False,
    engineio_logger=False,
    ping_timeout=120,
    ping_interval=20,
    message_queue=os.environ.get("REDIS_URL"),  # Essential: Allows Celery workers to emit to Web clients
    channel="flask-socketio",
    manage_session=True,
    cookie=None,  # Disable cookies for socketio to avoid some session issues behind proxies
)

# Import state to allow job tracking
import state
from job_tracker import job_tracker
from socket_helper import get_socketio_emitter

job_tracker.set_emitter(get_socketio_emitter())

# Initialize Limiter
redis_url = os.environ.get("REDIS_URL")
if redis_url:
    limiter = Limiter(
        key_func=get_remote_address, storage_uri=redis_url, default_limits=["50000 per day", "10000 per hour"]
    )
else:
    # Fallback to memory (will warn)
    limiter = Limiter(key_func=get_remote_address, default_limits=["20000 per day", "5000 per hour"])

backup_manager = None
plugin_manager = None
cloud_manager = None
watcher_thread = None


# Helper function to get status (avoids circular import issues)
def get_system_status():
    """Get system status values safely"""
    watching = 0
    if state.watcher is not None:
        try:
            watching = len(getattr(state.watcher, "directories", set()))
        except:
            pass
    return {
        "scanning": state.scan_in_progress,
        "updating_titledb": state.is_titledb_update_running,
        "watching": watching > 0,
        "libraries": watching,
    }


# Logging configuration
formatter = ColoredFormatter(
    "[%(asctime)s.%(msecs)03d] %(levelname)s (%(module)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)

logging.basicConfig(level=logging.INFO, handlers=[handler])

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


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Configure SQLite pragmas for better performance and concurrency"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")  # 30 seconds timeout for locked DB
    cursor.close()


# ===== LEGACY FUNCTIONS - TO BE REFACTORED =====
# These functions are kept for backward compatibility
# They should be moved to appropriate service modules in the future


@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login"""
    return db.session.get(User, int(user_id))


def reload_conf():
    """Reload application settings"""
    global app_settings
    app_settings = load_settings()


def on_library_change(events):
    """Handle library file changes"""
    logger.debug(f"Library change detected: {len(events)} events")

    with app.app_context():
        files_added = []
        files_deleted = []
        files_modified = []

        for event in events:
            if event.type == "created":
                files_added.append(event.src_path)
            elif event.type == "deleted":
                files_deleted.append(event.src_path)
                delete_file_by_filepath(event.src_path)
            elif event.type == "modified":
                logger.debug(f"Modified file detected: {event.src_path}")
                files_modified.append(event.src_path)
            elif event.type == "moved":
                if file_exists_in_db(event.src_path):
                    update_file_path(event.directory, event.src_path, event.dest_path)
                else:
                    files_added.append(event.dest_path)

        # Process additions and modifications (which may be new files being written)
        all_new_files = files_added + files_modified
        if all_new_files:
            directories = list(set(e.directory for e in events if e.type in ["created", "modified", "moved"]))

            for library_path in directories:
                files_to_process = [f for f in all_new_files if f.startswith(library_path)]

                if files_to_process:
                    logger.debug(f"Processing {len(files_to_process)} new/modified files in {library_path}")

                    # Add files to DB (this handles upserts/updates)
                    add_files_to_library(library_path, files_to_process)

                    # Identify files
                    # Identify files
                    if CELERY_ENABLED:
                        from tasks import identify_file_async

                        # Queue identification for each file
                        for filepath in files_to_process:
                            identify_file_async.delay(filepath)
                        logger.info(f"Queued async identification for {len(files_to_process)} files")
                    else:
                        # CRITICAL FIX: Use new identify_single_file function
                        from library import identify_single_file

                        logger.info(f"Identifying {len(files_to_process)} files individually")
                        for filepath in files_to_process:
                            logger.info(f"Identifying file: {filepath}")
                            identify_single_file(filepath)

        # CRITICAL: Always call post_library_change to update cache and notifying frontend
        # This fixes issues where badges/filters wouldn't update after new files were added
        if files_added or files_deleted or files_modified:
            logger.info("Invalidating library cache and updating titles after file changes")
            # If not using Celery, run synchronously. If using Celery, we run it here too to ensure
            # UI updates for non-identification changes (like deletions), although identification
            # tasks will also trigger updates.
            post_library_change()


def update_titledb_job(force=False):
    """Update TitleDB in background"""
    with app.app_context():
        from job_tracker import job_tracker
        from socket_helper import get_socketio_emitter

        # Configure emitter antes de registrar job
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
            import time
            time.sleep(0.1)

            job_tracker.update_progress(job_id, 1, 10, "Downloading TitleDB files...")
            current_settings = load_settings()
            import titledb

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
                except:
                    pass

            # Step 2: Reload memory cache
            # titles.load_titledb will call progress_cb
            titles.load_titledb(force=True, progress_callback=progress_cb)

            # Step 3: Sync to SQLite (The title data itself)
            job_tracker.update_progress(job_id, 5, 10, "Syncing database metadata...")
            add_missing_apps_to_db()
            update_titles()

            # Step 4: Optional Library identification
            # We only do this if specifically needed, or we do it faster
            from library import get_libraries, invalidate_library_cache
            
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
            except:
                pass
            job_tracker.fail_job(job_id, str(e))
            return False
        finally:
            with state.titledb_update_lock:
                state.is_titledb_update_running = False


def scan_library_job():
    """Scan library in background"""
    with app.app_context():
        # Track job
        job_id = job_tracker.register_job("aggregate_scan")
        job_tracker.start_job(job_id)

        with state.titledb_update_lock:
            if state.is_titledb_update_running:
                logger.info("Skipping library scan: update_titledb job is in progress.")
                job_tracker.fail_job(job_id, "TitleDB update in progress")
                return

        logger.info("Starting library scan job...")
        
        # Check if there are already active scan jobs
        active_jobs = job_tracker.get_active_jobs()
        active_scan_jobs = [j for j in active_jobs if j.get('type') in ['library_scan', 'aggregate_scan', 'file_identification']]
        
        if active_scan_jobs:
            logger.warning(f"Skipping library scan: {len(active_scan_jobs)} scan job(s) already in progress.")
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
                else:
                    from library import scan_library_path, identify_library_files, get_libraries
    
                    libraries = get_libraries()
                    logger.info(f"Found {len(libraries)} libraries to scan")
                    for i, lib in enumerate(libraries):
                        job_tracker.update_progress(job_id, i + 1, len(libraries), f"Scanning {lib.path}...")
                        logger.info(f"Scanning library: {lib.path}")
                        scan_library_path(lib.path)
    
                        job_tracker.update_progress(job_id, i + 1, len(libraries), f"Identifying files in {lib.path}...")
                        logger.info(f"Scan complete for {lib.path}, starting identification")
                        identify_library_files(lib.path)
                        logger.info(f"Identification complete for {lib.path}")
    
                # No need to call post_library_change here as scan_library_path now does it
            log_activity("library_scan_completed")
            logger.info("Library scan job completed successfully.")
            job_tracker.complete_job(job_id, {"total_libraries": len(get_libraries())})
        except Exception as e:
            logger.error(f"Error during library scan job: {e}")
            log_activity("library_scan_failed", details={"error": str(e)})
            job_tracker.fail_job(job_id, str(e))
        finally:
            with state.scan_lock:
                state.scan_in_progress = False


def create_automatic_backup():
    """Create automatic backup"""
    global backup_manager
    if backup_manager:
        logger.info("Starting automatic backup...")
        success, timestamp = backup_manager.create_backup()
        if success:
            logger.info(f"Automatic backup completed: {timestamp}")
        else:
            logger.error("Automatic backup failed")


def init_internal(app):
    """Initialize internal components"""
    global watcher_thread

    # Staged initialization to prevent CPU spike killing Gunicorn worker
    def stage1_cache():
        logger.info("Init Stage 1: Pre-loading Library Cache...")
        try:
            from library import load_library_from_disk

            saved = load_library_from_disk()
            if saved and "library" in saved:
                import library

                library._LIBRARY_CACHE = saved["library"]
                logger.info(f"Pre-loaded {len(saved['library'])} items from disk cache")
        except Exception as e:
            logger.warning(f"Stage 1 failed: {e}")

        # Schedule Stage 2
        threading.Timer(10.0, stage2_watchdog).start()

    def stage2_watchdog():
        logger.info("Init Stage 2: initializing Watchdog...")
        with app.app_context():
            state.watcher = Watcher(on_library_change)
            watcher_thread = threading.Thread(target=state.watcher.run)
            watcher_thread.daemon = True
            watcher_thread.start()

            # Setup paths but don't scan yet
            library_paths = app_settings.get("library", {}).get("paths", [])
            init_libraries(app, state.watcher, library_paths)
            logger.info(f"Initialized {len(library_paths)} library paths")

        # Schedule Stage 3
        threading.Timer(15.0, stage3_scan).start()

    def stage3_scan():
        logger.info("Init Stage 3: Checking for updates/scans...")
        with app.app_context():
            check_initial_scan(app)

    # Start Stage 1 after 5 seconds (fast boot)
    threading.Timer(5.0, stage1_cache).start()

    # Initialize job scheduler immediately (it's light)
    init_scheduler(app)

    # Schedule metadata fetch (2x per day = every 12h)
    from metadata_service import metadata_fetcher
    from datetime import timedelta

    app.scheduler.add_job(
        job_id="scheduled_metadata_fetch",
        func=lambda: metadata_fetcher.fetch_all_metadata(force=False),
        interval=timedelta(hours=12),
        run_first=False,  # Do NOT run on boot to save resources
    )
    logger.info("Scheduled automated metadata fetch (every 12 hours)")


def check_initial_scan(app):
    """Logic to determine if initial scan is needed"""
    try:
        # Load TitleDB info locally without updating yet
        # ...
        pass
    except Exception as e:
        logger.error(f"Error in check_initial_scan: {e}")

    # Simplified check logic moved from original init_internal
    # ...
    # We call the jobs in background threads as before
    with app.app_context():
        libs = get_libraries()
        critical_files = ["cnmts.json", "versions.json"]
        import os
        from constants import TITLEDB_DIR

        titledb_missing = any(not os.path.exists(os.path.join(TITLEDB_DIR, f)) for f in critical_files)

        if not libs or any(l.last_scan is None for l in libs) or titledb_missing:
            if titledb_missing:
                logger.info("Initial scan required: TitleDB critical files are missing.")
                threading.Thread(
                    target=lambda: update_titledb_job(force=True) if "app" in globals() else None, daemon=True
                ).start()
            else:
                logger.info("Initial scan required: New or un-scanned libraries detected.")
                threading.Thread(target=scan_library_job, daemon=True).start()

    if hasattr(app, "scheduler"):
        app.scheduler.add_job(
            job_id="update_db_and_scan",
            func=lambda: (update_titledb_job(), scan_library_job()),
            interval=timedelta(hours=24),
            run_first=False,
        )

        app.scheduler.add_job(
            job_id="refresh_titledb_remote_dates",
            func=lambda: titledb.get_source_manager().refresh_remote_dates(),
            interval=timedelta(hours=6),
            run_first=True,
        )

        # Weekly metadata refresh for existing games
        if CELERY_ENABLED:
            app.scheduler.add_job(
                job_id="metadata_refresh",
                func=lambda: fetch_metadata_for_all_games_async.delay(),
                interval=timedelta(days=7),
                run_first=False,
            )

        app.scheduler.add_job(
            job_id="daily_backup",
            func=create_automatic_backup,
            interval=timedelta(days=1),
            run_first=False,
            start_date=now_utc().replace(hour=3, minute=0, second=0, microsecond=0),
        )

    log_activity("system_startup", details={"version": BUILD_VERSION})


def create_app():
    """Application factory"""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = MYFOIL_DB
    app.config["SECRET_KEY"] = get_or_create_secret_key()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {
            "timeout": 30  # SQLite busy timeout in seconds
        }
    }

    # Initialize components
    db.init_app(app)
    migrate.init_app(app, db)

    # Initialize login manager
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    limiter.init_app(app)

    # Initialize I18n
    app.i18n = I18n(app)

    # Register exception handlers
    from exceptions import register_exception_handlers

    register_exception_handlers(app)

    # Register blueprints
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(web_bp)
    app.register_blueprint(system_web_bp)
    app.register_blueprint(library_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(wishlist_bp)
    app.register_blueprint(upcoming_bp)

    @app.route("/upcoming")
    @access_required("shop")
    def upcoming_page():
        """Upcoming games page"""
        return render_template("upcoming.html", title="Upcoming")

    # Initialize REST API
    api_bp = Blueprint("api", __name__, url_prefix="/api")
    init_rest_api(api_bp)
    app.register_blueprint(api_bp)

    # Initialize metrics
    init_metrics(app)

    # Initialize SocketIO with already configured object
    socketio.init_app(app)

    # Add Cache-Control headers for static files
    @app.after_request
    def add_cache_control_headers(response):
        """
        Prevent aggressive caching of static assets to avoid stale JS/CSS issues.

        Strategy:
        - JS/CSS: Force revalidation on every request (no-cache)
        - Images/Fonts: Allow 1 hour browser cache (performance)
        - API responses: No caching (already handled per-endpoint)
        """
        from flask import request

        if request.path.startswith("/static/"):
            # Force revalidation for JS/CSS to prevent stale code
            if request.path.endswith((".js", ".css")):
                response.headers["Cache-Control"] = "no-cache, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            # Allow reasonable caching for images/fonts (performance)
            elif request.path.endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".woff", ".woff2", ".ttf", ".eot")
            ):
                response.headers["Cache-Control"] = "public, max-age=3600"

        return response

    # SocketIO event handlers
    @socketio.on("connect")
    def handle_connect():
        logger.info("Client connected")

    @socketio.on("disconnect")
    def handle_disconnect():
        logger.info("Client disconnected")

    # Global initialization
    with app.app_context():
        global backup_manager, plugin_manager, cloud_manager

        # Initialize managers
        backup_manager = BackupManager(CONFIG_DIR, DATA_DIR)

        # Load settings
        reload_conf()

        # Initialize database
        init_db(app)
        init_users(app)

        # Initialize job tracker with app context
        from job_tracker import job_tracker

        job_tracker.init_app(app)

        # Initialize file watcher and libraries
        init_internal(app)

        # Initialize plugins
        plugin_manager = get_plugin_manager(PLUGINS_DIR, app)
        disabled_plugins = app_settings.get("plugins", {}).get("disabled", [])
        plugin_manager.load_plugins(disabled_plugins)

        # Initialize cloud manager
        cloud_manager = get_cloud_manager(CONFIG_DIR)

    # Job scheduler already initialized in init_internal

    if CELERY_ENABLED:
        logger.info("Celery tasks loaded and enabled.")

    return app


# Create app instance
app = create_app()

if __name__ == "__main__":
    logger.info(f"Build Version: {BUILD_VERSION}")
    logger.info("Starting server on port 8465...")
    socketio.run(app, debug=True, use_reloader=False, host="0.0.0.0", port=8465, allow_unsafe_werkzeug=True)
    logger.info("Shutting down server...")
