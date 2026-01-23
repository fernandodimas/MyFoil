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
from jobs.scheduler import JobScheduler

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

# Global variables
app_settings = {}

# Initialize SocketIO with production-ready configuration
# - cors_allowed_origins="*": Allow connections from any domain (safe for this use case)
# - async_mode='gevent': Use gevent for async operations (already monkey-patched)
# - logger=True, engineio_logger=True: Enable detailed logging for debugging
# - ping_timeout=60, ping_interval=25: Longer timeouts for connections behind proxies
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode='gevent',
    logger=True,
    engineio_logger=True,
    ping_timeout=60,
    ping_interval=25,
    message_queue=os.environ.get("REDIS_URL"),  # Essential: Allows Celery workers to emit to Web clients
    # Explicit configuration for pub/sub
    channel='flask-socketio',  # Ensure consistent channel name
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
        key_func=get_remote_address, storage_uri=redis_url, default_limits=["5000 per day", "2000 per hour"]
    )
else:
    # Fallback to memory (will warn)
    limiter = Limiter(key_func=get_remote_address, default_limits=["1000 per day", "500 per hour"])

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
    """Configure SQLite pragmas for better performance"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
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
    logger.info(f"Library change detected: {len(events)} events")
    with app.app_context():
        action_events = [e for e in events if e.type == "created"]
        other_events = [e for e in events if e.type != "created"]

        for event in other_events:
            if event.type == "moved":
                if file_exists_in_db(event.src_path):
                    update_file_path(event.directory, event.src_path, event.dest_path)
                else:
                    event.src_path = event.dest_path
                    action_events.append(event)

            elif event.type == "deleted":
                delete_file_by_filepath(event.src_path)

            elif event.type == "modified":
                logger.info(f"Modified file detected: {event.src_path}")
                # Treat modified as a trigger for identification/update
                action_events.append(event)

        if action_events:
            directories = list(set(e.directory for e in action_events))
            for library_path in directories:
                files_to_process = [e.src_path for e in action_events if e.directory == library_path]
                logger.info(f"Processing {len(files_to_process)} files in library: {library_path}")
                
                # add_files_to_library now handles upsert
                add_files_to_library(library_path, files_to_process)

                if CELERY_ENABLED:
                    # To avoid storm of tasks, trigger one identification task per library
                    from tasks import identify_file_async
                    identify_file_async.delay(files_to_process[0]) 
                    logger.info(f"Queued async identification for library {library_path}")
                else:
                    from library import identify_library_files
                    logger.info(f"Identifying files in {library_path}")
                    identify_library_files(library_path)

    if not CELERY_ENABLED:
        # post_library_change common logic (update_titles, generate_library, invalidate cache)
        post_library_change()
    else:
        post_library_change()  # For now, still call to update UI state


def update_titledb_job(force=False):
    """Update TitleDB in background"""
    with state.titledb_update_lock:
        if state.is_titledb_update_running:
            logger.info("TitleDB update already in progress.")
            return False
        state.is_titledb_update_running = True

    logger.info("Starting TitleDB update job...")
    try:
        current_settings = load_settings()
        import titledb

        # Perform update within app context to allow DB sync during load_titledb
        if "app" in globals():
            with app.app_context():
                titledb.update_titledb(current_settings, force=force)

                logger.info("Syncing new TitleDB versions to library...")
                add_missing_apps_to_db()
                update_titles()
                # Re-identify files that were identified by filename (now TitleDB has more data)
                from library import identify_library_files, get_libraries

                libraries = get_libraries()
                for library in libraries:
                    identify_library_files(library.path)
                generate_library(force=True)
                logger.info("Library cache regenerated after TitleDB update.")
        else:
             # Fallback for standalone scripts (won't sync to DB)
             titledb.update_titledb(current_settings, force=force)

        logger.info("TitleDB update job completed.")
        return True
    except Exception as e:
        logger.error(f"Error during TitleDB update job: {e}")
        log_activity("titledb_update_failed", details={"error": str(e)})
        return False
    finally:
        with state.titledb_update_lock:
            state.is_titledb_update_running = False


def scan_library_job():
    """Scan library in background"""
    with state.titledb_update_lock:
        if state.is_titledb_update_running:
            logger.info(
                "Skipping scheduled library scan: update_titledb job is currently in progress. Rescheduling in 5 minutes."
            )
            if "app" in globals() and hasattr(app, "scheduler"):
                app.scheduler.add_job(
                    job_id=f"scan_library_rescheduled_{datetime.datetime.now().timestamp()}",
                    func=scan_library_job,
                    run_once=True,
                    start_date=datetime.datetime.now().replace(microsecond=0) + timedelta(minutes=5),
                )
            return

    logger.info("Starting library scan job...")
    with state.scan_lock:
        if state.scan_in_progress:
            logger.info("Skipping library scan: scan already in progress.")
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
                for lib in libraries:
                    logger.info(f"Scanning library: {lib.path}")
                    scan_library_path(lib.path)
                    logger.info(f"Scan complete for {lib.path}, starting identification")
                    identify_library_files(lib.path)
                    logger.info(f"Identification complete for {lib.path}")
                post_library_change()
        log_activity("library_scan_completed")
        logger.info("Library scan job completed.")
    except Exception as e:
        logger.error(f"Error during library scan job: {e}")
        log_activity("library_scan_failed", details={"error": str(e)})
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
    logger.info("Initializing File Watcher...")
    state.watcher = Watcher(on_library_change)
    watcher_thread = threading.Thread(target=state.watcher.run)
    watcher_thread.daemon = True
    watcher_thread.start()

    library_paths = app_settings.get("library", {}).get("paths", [])
    init_libraries(app, state.watcher, library_paths)

    # Initialize job scheduler
    from jobs.scheduler import JobScheduler

    job_scheduler = JobScheduler()
    job_scheduler.init_app(app)

    # Check for initial scan
    run_now = False
    with app.app_context():
        # Log active TitleDB source
        try:
            import titledb

            active_src = titledb.get_active_source_info()
            if active_src:
                logger.info(
                    f"Active TitleDB source: {active_src.get('name', 'Unknown')} (last download: {active_src.get('last_download_date', 'N/A')}, titles: {active_src.get('titles_count', 0)})"
                )
            else:
                logger.warning("No active TitleDB source configured")
        except Exception as e:
            logger.warning(f"Could not get active TitleDB source: {e}")

        libs = get_libraries()

        critical_files = ["cnmts.json", "versions.json"]
        import os
        from constants import TITLEDB_DIR

        titledb_missing = any(not os.path.exists(os.path.join(TITLEDB_DIR, f)) for f in critical_files)

        if not libs or any(l.last_scan is None for l in libs) or titledb_missing:
            run_now = True
            if titledb_missing:
                logger.info("Initial scan required: TitleDB critical files are missing.")

                # Force update TitleDB at startup (same logic as settings page)
                def run_titledb_update():
                    with app.app_context():
                        update_titledb_job(force=True)

                threading.Thread(target=run_titledb_update, daemon=True).start()
            else:
                logger.info("Initial scan required: New or un-scanned libraries detected.")

                # Start library scan in background
                def run_library_scan():
                    with app.app_context():
                        scan_library_job()

                threading.Thread(target=run_library_scan, daemon=True).start()

    if hasattr(app, "scheduler"):
        app.scheduler.add_job(
            job_id="update_db_and_scan",
            func=lambda: (update_titledb_job(), scan_library_job()),
            interval=timedelta(hours=24),
            run_first=False,
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
            start_date=datetime.datetime.now().replace(hour=3, minute=0, second=0, microsecond=0),
        )

    log_activity("system_startup", details={"version": BUILD_VERSION})


def create_app():
    """Application factory"""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = MYFOIL_DB
    app.config["SECRET_KEY"] = get_or_create_secret_key()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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

    # Initialize SocketIO
    socketio.init_app(app, cors_allowed_origins="*", async_mode="gevent", engineio_logger=False, logger=False)

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
        
        if request.path.startswith('/static/'):
            # Force revalidation for JS/CSS to prevent stale code
            if request.path.endswith(('.js', '.css')):
                response.headers['Cache-Control'] = 'no-cache, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
            # Allow reasonable caching for images/fonts (performance)
            elif request.path.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.woff', '.woff2', '.ttf', '.eot')):
                response.headers['Cache-Control'] = 'public, max-age=3600'
        
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

        # Initialize file watcher and libraries
        init_internal(app)

        # Initialize plugins
        plugin_manager = get_plugin_manager(PLUGINS_DIR, app)
        disabled_plugins = app_settings.get("plugins", {}).get("disabled", [])
        plugin_manager.load_plugins(disabled_plugins)

        # Initialize cloud manager
        cloud_manager = get_cloud_manager(CONFIG_DIR)

    # Initialize job scheduler
    job_scheduler = JobScheduler()
    job_scheduler.init_app(app)

    if CELERY_ENABLED:
        logger.info("Celery tasks loaded and enabled.")

    return app


# Create app instance
app = create_app()

if __name__ == "__main__":
    logger.info(f"Build Version: {BUILD_VERSION}")
    logger.info("Starting server on port 8465...")
    socketio.run(app, debug=False, use_reloader=False, host="0.0.0.0", port=8465)
    logger.info("Shutting down server...")
