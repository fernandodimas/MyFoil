"""
MyFoil - Enhanced Nintendo Switch Library Manager
Application Factory e Inicialização
"""
import warnings
import os
import sys
import logging

# Suppress Eventlet and Flask-Limiter warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="eventlet")
warnings.filterwarnings("ignore", category=UserWarning, module="flask_limiter")

import eventlet
eventlet.monkey_patch()

import flask.cli
flask.cli.show_server_banner = lambda *args: None

# Core Flask imports
from flask import Flask
from flask_login import LoginManager
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
from middleware.auth import access_required

# Jobs
from jobs.scheduler import JobScheduler

# Optional Celery for async tasks
try:
    from celery_app import celery
    from tasks import scan_library_async, identify_file_async
    CELERY_ENABLED = True
except ImportError as e:
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
import hmac
import hashlib
import requests

# Global variables
app_settings = {}
socketio = SocketIO()
limiter = Limiter(key_func=get_remote_address, default_limits=["300 per day", "100 per hour"])
backup_manager = None
scan_in_progress = False
scan_lock = threading.Lock()
is_titledb_update_running = False
titledb_update_lock = threading.Lock()
plugin_manager = None
cloud_manager = None

# Logging configuration
formatter = ColoredFormatter(
    '[%(asctime)s.%(msecs)03d] %(levelname)s (%(module)s) %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[handler]
)

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
        structlog.processors.JSONRenderer() if os.environ.get('LOG_FORMAT') == 'json' else structlog.dev.ConsoleRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger('main')

# Apply filter to hide date from http access logs
logging.getLogger('werkzeug').addFilter(FilterRemoveDateFromWerkzeugLogs())
logging.getLogger('alembic.runtime.migration').setLevel(logging.WARNING)

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
    with app.app_context():
        created_events = [e for e in events if e.type == 'created']
        modified_events = [e for e in events if e.type != 'created']

        for event in modified_events:
            if event.type == 'moved':
                if file_exists_in_db(event.src_path):
                    update_file_path(event.directory, event.src_path, event.dest_path)
                else:
                    event.src_path = event.dest_path
                    created_events.append(event)

            elif event.type == 'deleted':
                delete_file_by_filepath(event.src_path)

            elif event.type == 'modified':
                add_files_to_library(event.directory, [event.src_path])

        if created_events:
            directories = list(set(e.directory for e in created_events))
            for library_path in directories:
                new_files = [e.src_path for e in created_events if e.directory == library_path]
                add_files_to_library(library_path, new_files)

                if CELERY_ENABLED:
                    for f_path in new_files:
                        identify_file_async.delay(f_path)
                    logger.info(f"Queued async identification for {len(new_files)} files in {library_path}")

    if not CELERY_ENABLED:
        post_library_change()
    else:
        post_library_change()  # For now, still call to update UI state

def update_titledb_job(force=False):
    """Update TitleDB in background"""
    global is_titledb_update_running
    with titledb_update_lock:
        if is_titledb_update_running:
            logger.info("TitleDB update already in progress.")
            return False
        is_titledb_update_running = True

    logger.info("Starting TitleDB update job...")
    try:
        current_settings = load_settings()
        import titledb
        titledb.update_titledb(current_settings, force=force)

        if 'app' in globals():
            with app.app_context():
                logger.info("Syncing new TitleDB versions to library...")
                add_missing_apps_to_db()
                update_titles()
                generate_library(force=True)
                logger.info("Library cache regenerated after TitleDB update.")

        logger.info("TitleDB update job completed.")
        return True
    except Exception as e:
        logger.error(f"Error during TitleDB update job: {e}")
        log_activity('titledb_update_failed', details={'error': str(e)})
        return False
    finally:
        with titledb_update_lock:
            is_titledb_update_running = False

def scan_library_job():
    """Scan library in background"""
    global is_titledb_update_running
    with titledb_update_lock:
        if is_titledb_update_running:
            logger.info("Skipping scheduled library scan: update_titledb job is currently in progress. Rescheduling in 5 minutes.")
            if 'app' in globals() and hasattr(app, 'scheduler'):
                app.scheduler.add_job(
                    job_id=f'scan_library_rescheduled_{datetime.datetime.now().timestamp()}',
                    func=scan_library_job,
                    run_once=True,
                    start_date=datetime.datetime.now().replace(microsecond=0) + timedelta(minutes=5)
                )
            return

    logger.info("Starting library scan job...")
    global scan_in_progress
    with scan_lock:
        if scan_in_progress:
            logger.info('Skipping library scan: scan already in progress.')
            return
        scan_in_progress = True
    try:
        from metrics import ACTIVE_SCANS
        with ACTIVE_SCANS.track_inprogress():
            if CELERY_ENABLED:
                from tasks import scan_all_libraries_async
                scan_all_libraries_async.delay()
                logger.info("Scheduled library scan queued to Celery.")
            else:
                scan_library()
                post_library_change()
        log_activity('library_scan_completed')
        logger.info("Library scan job completed.")
    except Exception as e:
        logger.error(f"Error during library scan job: {e}")
        log_activity('library_scan_failed', details={'error': str(e)})
    finally:
        with scan_lock:
            scan_in_progress = False

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
    global watcher, watcher_thread
    logger.info('Initializing File Watcher...')
    watcher = Watcher(on_library_change)
    watcher_thread = threading.Thread(target=watcher.run)
    watcher_thread.daemon = True
    watcher_thread.start()

    library_paths = app_settings.get('library', {}).get('paths', [])
    init_libraries(app, watcher, library_paths)

    # Initialize job scheduler
    from jobs.scheduler import JobScheduler
    job_scheduler = JobScheduler()
    job_scheduler.init_app(app)

    # Check for initial scan
    run_now = False
    with app.app_context():
        libs = get_libraries()

        critical_files = ['cnmts.json', 'versions.json']
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

    if hasattr(app, 'scheduler'):
        app.scheduler.add_job(
            job_id='update_db_and_scan',
            func=lambda: (update_titledb_job(), scan_library_job()),
            interval=timedelta(hours=24),
            run_first=False
        )

        app.scheduler.add_job(
            job_id='daily_backup',
            func=create_automatic_backup,
            interval=timedelta(days=1),
            run_first=False,
            start_date=datetime.datetime.now().replace(hour=3, minute=0, second=0, microsecond=0)
        )

    log_activity('system_startup', details={'version': BUILD_VERSION})

def create_app():
    """Application factory"""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = MYFOIL_DB
    app.config['SECRET_KEY'] = get_or_create_secret_key()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize components
    db.init_app(app)
    migrate.init_app(app, db)

    # Initialize login manager
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

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

    # Initialize REST API
    api_bp = Blueprint('api', __name__, url_prefix='/api')
    init_rest_api(api_bp)
    app.register_blueprint(api_bp)

    # Initialize metrics
    init_metrics(app)

    # Initialize SocketIO
    socketio.init_app(app,
        cors_allowed_origins="*",
        async_mode='eventlet',
        engineio_logger=False,
        logger=False
    )

    # SocketIO event handlers
    @socketio.on('connect')
    def handle_connect():
        logger.info('Client connected')

    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info('Client disconnected')

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
        disabled_plugins = app_settings.get('plugins', {}).get('disabled', [])
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

if __name__ == '__main__':
    logger.info(f'Build Version: {BUILD_VERSION}')
    logger.info('Starting server on port 8465...')
    socketio.run(app, debug=False, use_reloader=False, host="0.0.0.0", port=8465)
    logger.info('Shutting down server...')