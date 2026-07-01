import os
import sys
import logging
import threading
import time
from datetime import timedelta

import flask.cli
from flask import Flask, render_template, Blueprint
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

flask.cli.show_server_banner = lambda *args: None

logging.getLogger("engineio.server").setLevel(logging.CRITICAL)
logging.getLogger("socketio.server").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
logging.getLogger("geventwebsocket.handler").setLevel(logging.WARNING)
logging.getLogger("geventwebsocket.server").setLevel(logging.WARNING)

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
# from rest_api import init_rest_api  # DISABLED: broken imports - see rest_api.py
import structlog
from metrics import init_metrics
from backup import BackupManager
from plugin_system import get_plugin_manager

from routes.library import library_bp
from routes.settings import settings_bp
from routes.system import system_bp, system_web_bp
from routes.web import web_bp
from routes.wishlist import wishlist_bp
from routes.upcoming import upcoming_bp
from scheduler import init_scheduler

try:
    from celery_app import celery  # noqa: F401
    from tasks import fetch_metadata_for_all_games_async
    import redis
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    r = redis.from_url(redis_url)
    try:
        r.ping()
        CELERY_ENABLED = True
        logging.info("Redis connection established - Async background tasks enabled (Celery)")
    except Exception as redis_error:
        if os.environ.get("CELERY_REQUIRED", "false").lower() == "true":
            logging.error(f"Redis required but not reachable: {redis_error}")
            CELERY_ENABLED = False
        else:
            logging.info("Redis not available - Async background tasks disabled (Celery)")
            CELERY_ENABLED = False
except ImportError:
    CELERY_ENABLED = False

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
from utils import now_utc, ColoredFormatter, get_or_create_secret_key
import library as library_mod
from file_watcher import Watcher

import state
from job_tracker import job_tracker
from socket_helper import get_socketio_emitter
from exceptions import register_exception_handlers

app_settings = {}


class SafeSocketIO(SocketIO):
    def __call__(self, environ, start_response):
        try:
            return super().__call__(environ, start_response)
        except KeyError as e:
            if "Session is disconnected" in str(e) or "Session is closed" in str(e):
                status = "400 Bad Request"
                response_headers = [("Content-type", "text/plain")]
                start_response(status, response_headers)
                return [b"Session is disconnected"]
            raise


_cors_raw = os.environ.get("SOCKETIO_CORS_ORIGINS", "http://localhost:8465")
_cors_origins = [o.strip() for o in _cors_raw.split(",")] if "," in _cors_raw else _cors_raw
socketio = SafeSocketIO(
    cors_allowed_origins=_cors_origins,
    async_mode="gevent",
    logger=False,
    engineio_logger=False,
    ping_timeout=120,
    ping_interval=20,
    message_queue=os.environ.get("REDIS_URL"),
    channel="flask-socketio",
    manage_session=False,
    cookie=None,
)

job_tracker.set_emitter(get_socketio_emitter())

redis_url = os.environ.get("REDIS_URL")
if redis_url:
    limiter = Limiter(
        key_func=get_remote_address, storage_uri=redis_url, default_limits=["50000 per day", "10000 per hour"]
    )
else:
    limiter = Limiter(key_func=get_remote_address, default_limits=["20000 per day", "5000 per hour"])

backup_manager = None
plugin_manager = None
_current_app = None

formatter = ColoredFormatter(
    "[%(asctime)s.%(msecs)03d] %(levelname)s (%(module)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)

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

logger = logging.getLogger("main")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def on_library_change(events):
    logger.debug(f"Library change detected: {len(events)} events")

    with _current_app.app_context():
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

        all_new_files = files_added + files_modified
        if all_new_files:
            directories = list(set(e.directory for e in events if e.type in ["created", "modified", "moved"]))

            for library_path in directories:
                files_to_process = [f for f in all_new_files if f.startswith(library_path)]

                if files_to_process:
                    logger.debug(f"Processing {len(files_to_process)} new/modified files in {library_path}")
                    add_files_to_library(library_path, files_to_process)

                    if CELERY_ENABLED:
                        from tasks import identify_file_async

                        for filepath in files_to_process:
                            identify_file_async.delay(filepath)
                        logger.info(f"Queued async identification for {len(files_to_process)} files")
                    else:
                        from library import identify_single_file

                        logger.info(f"Identifying {len(files_to_process)} files individually")
                        for filepath in files_to_process:
                            logger.info(f"Identifying file: {filepath}")
                            identify_single_file(filepath)

        if files_added or files_deleted or files_modified:
            logger.info("Invalidating library cache and updating titles after file changes")
            post_library_change()


def init_internal(app):
    logger.info("=" * 80)
    logger.info("STARTUP: Cleaning up stale jobs from previous session...")
    logger.info("=" * 80)
    job_tracker.cleanup_stale_jobs()
    logger.info("STARTUP: Job cleanup completed")

    logger.info("Startup: Stage 0 - Loading library cache from disk...")
    try:
        from library import load_library_from_disk

        saved = load_library_from_disk()
        if saved and "library" in saved:
            library_mod.LIBRARY_CACHE.data = saved["library"]
            logger.info(f"Pre-loaded {len(saved['library'])} items from disk cache (READY)")
        else:
            logger.info("No cache found, library will be generated on first request")
    except Exception as e:
        logger.warning(f"Stage 0 cache load failed: {e}")

    def _load_titledb_async():
        try:
            with app.app_context():
                logger.info("Background: Loading TitleDB cache...")
                titles.load_titledb()
                logger.info("TitleDB loaded successfully in background")
        except Exception as e:
            logger.error(f"Background TitleDB load failed: {e}")

    titledb_thread = threading.Thread(target=_load_titledb_async, daemon=True, name="titledb-loader")
    titledb_thread.start()
    logger.info("TitleDB loading started in background (non-blocking)")

    def stage1_cache():
        logger.info("Init Stage 1: Verifying library cache...")
        try:
            if library_mod.LIBRARY_CACHE.data:
                logger.info(f"Library cache verified: {len(library_mod.LIBRARY_CACHE.data)} items")
            else:
                logger.info("No cache in memory, will load on first request")
        except Exception as e:
            logger.warning(f"Stage 1 verification failed: {e}")

        threading.Timer(2.0, stage2_watchdog).start()

    def stage2_watchdog():
        logger.info("Init Stage 2: initializing Watchdog...")
        with app.app_context():
            state.watcher = Watcher(on_library_change)

            state.watcher.run()

            time.sleep(0.2)

            try:
                libs_db = db_module.get_libraries()
                yaml_paths = app_settings.get("library", {}).get("paths", [])

                db_paths = set(lib.path for lib in libs_db)
                changes_made = False

                for p in yaml_paths:
                    if p not in db_paths:
                        logger.info(f"Syncing path from YAML to DB: {p}")
                        db_module.add_library(p)
                        changes_made = True

                if changes_made:
                    libs_db = db_module.get_libraries()

                library_paths = [lib.path for lib in libs_db]
                logger.info(f"Loaded {len(library_paths)} library paths from Database for Watchdog.")
            except Exception as e:
                logger.error(f"Failed to load libraries from DB for Watchdog: {e}. Falling back to settings.")
                library_paths = app_settings.get("library", {}).get("paths", [])

            init_libraries(app, state.watcher, library_paths)
            logger.info(f"Initialized {len(library_paths)} library paths")

        threading.Timer(5.0, stage3_scan).start()

    def stage3_scan():
        logger.info("Init Stage 3: Checking for updates/scans...")
        with app.app_context():
            check_initial_scan(app)

    threading.Timer(1.0, stage1_cache).start()

    init_scheduler(app)

    from metadata_service import metadata_fetcher

    app.scheduler.add_job(
        job_id="scheduled_metadata_fetch",
        func=lambda: metadata_fetcher.fetch_all_metadata(force=False),
        interval=timedelta(hours=24),
        run_first=False,
    )
    logger.info("Scheduled automated metadata fetch (every 24 hours)")


def check_initial_scan(app):
    from datetime import datetime, timezone
    from constants import TITLEDB_DIR

    with app.app_context():
        libs = db_module.get_libraries()
        critical_files = ["cnmts.json", "versions.json"]

        titledb_missing = any(not os.path.exists(os.path.join(TITLEDB_DIR, f)) for f in critical_files)

        titledb_outdated = False
        if not titledb_missing:
            try:
                cutoff = datetime.now(timezone.utc).timestamp() - (24 * 3600)
                for f in critical_files:
                    fp = os.path.join(TITLEDB_DIR, f)
                    if os.path.getmtime(fp) < cutoff:
                        titledb_outdated = True
                        logger.info(f"TitleDB file {f} is outdated, will trigger update.")
                        break
            except Exception as e:
                logger.warning(f"Error checking TitleDB age: {e}")

        if titledb_missing or titledb_outdated:
            if titledb_missing:
                logger.info("Initial scan required: TitleDB critical files are missing.")
            else:
                logger.info("Initial scan required: TitleDB critical files are outdated.")
            threading.Thread(
                target=lambda: _update_titledb_job(force=True), daemon=True
            ).start()
        elif not libs or any(l.last_scan is None for l in libs):
            logger.info("Initial scan required: New or un-scanned libraries detected.")
            threading.Thread(target=_scan_library_job, daemon=True).start()

    if hasattr(app, "scheduler"):
        app.scheduler.add_job(
            job_id="update_db_and_scan",
            func=lambda: (_update_titledb_job(), _scan_library_job()),
            interval=timedelta(hours=24),
            run_first=False,
        )

        app.scheduler.add_job(
            job_id="refresh_titledb_remote_dates",
            func=lambda: titledb.get_source_manager().refresh_remote_dates(),
            interval=timedelta(hours=6),
            run_first=True,
        )

        app.scheduler.add_job(
            job_id="incremental_library_update",
            func=lambda: _incremental_library_update_job(),
            interval=timedelta(hours=6),
            run_first=False,
        )
        logger.info("Scheduled incremental library update (every 6 hours)")

        if CELERY_ENABLED:
            app.scheduler.add_job(
                job_id="metadata_refresh",
                func=lambda: fetch_metadata_for_all_games_async.delay(),
                interval=timedelta(days=7),
                run_first=False,
            )

        app.scheduler.add_job(
            job_id="daily_backup",
            func=_create_automatic_backup,
            interval=timedelta(days=1),
            run_first=False,
            start_date=now_utc().replace(hour=3, minute=0, second=0, microsecond=0),
        )

    log_activity("system_startup", details={"version": BUILD_VERSION})


def create_app(minimal=False):
    global _current_app

    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    if not MYFOIL_DB:
        raise RuntimeError("DATABASE_URL environment variable must be set for PostgreSQL")

    app.config["SQLALCHEMY_DATABASE_URI"] = MYFOIL_DB
    app.config["SECRET_KEY"] = get_or_create_secret_key()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    engine_options = {"pool_pre_ping": True}
    db_uri = str(app.config.get("SQLALCHEMY_DATABASE_URI", "")).lower()
    if not db_uri.startswith("sqlite"):
        engine_options.update(
            {
                "pool_size": 20,
                "max_overflow": 30,
                "pool_recycle": 3600,
            }
        )

    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options

    db.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    limiter.init_app(app)

    app.i18n = I18n(app)

    register_exception_handlers(app)

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
        return render_template("upcoming.html", title="Upcoming")

    # DISABLED: rest_api.py has broken imports - Flask-RESTX docs disabled until fixed
    # api_bp = Blueprint("api", __name__, url_prefix="/api")
    # init_rest_api(api_bp)
    # app.register_blueprint(api_bp)

    init_metrics(app)

    socketio.init_app(app)

    @app.after_request
    def add_cache_control_headers(response):
        from flask import request

        origin = request.headers.get("Origin")
        if origin:
            allowed = False
            if _cors_origins == "*":
                allowed = True
            elif isinstance(_cors_origins, list):
                allowed = origin in _cors_origins
            elif isinstance(_cors_origins, str):
                allowed = origin == _cors_origins

            if allowed:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Max-Age"] = "86400"

        if request.method == "OPTIONS":
            response.status_code = 204
            return response

        if request.path.startswith("/static/"):
            if request.path.endswith((".js", ".css")):
                response.headers["Cache-Control"] = "no-cache, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            elif request.path.endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".woff", ".woff2", ".ttf", ".eot")
            ):
                response.headers["Cache-Control"] = "public, max-age=3600"

        return response

    with app.app_context():
        global backup_manager, plugin_manager

        backup_manager = BackupManager(CONFIG_DIR, DATA_DIR)

        reload_conf()

        init_db(app)
        init_users(app)

        if not minimal:
            job_tracker.init_app(app)
            init_internal(app)

        plugin_manager = get_plugin_manager(PLUGINS_DIR, app)
        disabled_plugins = app_settings.get("plugins", {}).get("disabled", [])
        plugin_manager.load_plugins(disabled_plugins)

    if CELERY_ENABLED:
        logger.info("Celery tasks loaded and enabled.")

    _current_app = app
    return app


def _update_titledb_job(force=False):
    from app import update_titledb_job
    return update_titledb_job(force=force)


def _scan_library_job():
    from app import scan_library_job
    return scan_library_job()


def _create_automatic_backup():
    from app import create_automatic_backup
    return create_automatic_backup()


def _incremental_library_update_job():
    from app import incremental_library_update_job
    return incremental_library_update_job()
