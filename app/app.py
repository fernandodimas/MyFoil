import warnings
# Suppress Eventlet and Flask-Limiter warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="eventlet")
warnings.filterwarnings("ignore", category=UserWarning, module="flask_limiter")
import eventlet
eventlet.monkey_patch()
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, Response
from flask_login import LoginManager
from flask_socketio import SocketIO, emit
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from scheduler import init_scheduler
from functools import wraps
from file_watcher import Watcher
import threading
import logging
import sys
import copy
import flask.cli
import datetime
from datetime import timedelta
flask.cli.show_server_banner = lambda *args: None
from constants import *
from settings import *
from db import *
from shop import *
from auth import *
import titles
from utils import *
from library import *
import titledb
import os
from i18n import I18n
from sqlalchemy import event, func, and_, case
from sqlalchemy.engine import Engine
from rest_api import init_rest_api
import structlog
from metrics import init_metrics, ACTIVE_SCANS, IDENTIFICATION_DURATION
from backup import BackupManager
import hmac
import hashlib
import requests
from plugin_system import get_plugin_manager
from cloud_sync import get_cloud_manager

# Optional Celery for async tasks
try:
    from celery_app import celery
    from tasks import scan_library_async, identify_file_async
    CELERY_ENABLED = True
except ImportError as e:
    CELERY_ENABLED = False

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

def update_titledb_job(force=False):
    global is_titledb_update_running
    with titledb_update_lock:
        if is_titledb_update_running:
            logger.info("TitleDB update already in progress.")
            return False
        is_titledb_update_running = True
    
    logger.info("Starting TitleDB update job...")
    try:
        current_settings = load_settings()
        titledb.update_titledb(current_settings, force=force)
        
        # Sync DB with new versions from TitleDB
        # We need app context for DB operations
        if 'app' in globals():
            with app.app_context():
                logger.info("Syncing new TitleDB versions to library...")
                add_missing_apps_to_db()
                update_titles()
                
                # Regenerate library cache with new TitleDB data
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
    global is_titledb_update_running
    with titledb_update_lock:
        if is_titledb_update_running:
            logger.info("Skipping scheduled library scan: update_titledb job is currently in progress. Rescheduling in 5 minutes.")
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
        with ACTIVE_SCANS.track_inprogress():
            # Usar Celery se disponível para scans agendados também
            if CELERY_ENABLED:
                scan_all_libraries_async.delay()
                logger.info("Scheduled library scan queued to Celery.")
            else:
                scan_library()
                post_library_change()
        logger.info("Library scan job completed.")
        log_activity('library_scan_completed')
    except Exception as e:
        logger.error(f"Error during library scan job: {e}")
        log_activity('library_scan_failed', details={'error': str(e)})
    finally:
        with scan_lock:
            scan_in_progress = False

def update_db_and_scan_job():
    logger.info("Running update job (TitleDB update and library scan)...")
    update_titledb_job()
    scan_library_job()
    titledb.refresh_titledb_remote_dates()
    logger.info("Update job completed.")

def create_automatic_backup():
    """Scheduled job for automatic backups"""
    global backup_manager
    if backup_manager:
        logger.info("Starting automatic backup...")
        success, timestamp = backup_manager.create_backup()
        if success:
            logger.info(f"Automatic backup completed: {timestamp}")
        else:
            logger.error("Automatic backup failed")

def init_internal(app):
    global watcher
    global watcher_thread
    # Create and start the file watcher
    logger.info('Initializing File Watcher...')
    watcher = Watcher(on_library_change)
    watcher_thread = threading.Thread(target=watcher.run)
    watcher_thread.daemon = True
    watcher_thread.start()

    # init libraries
    library_paths = app_settings.get('library', {}).get('paths', [])
    init_libraries(app, watcher, library_paths)

     # Initialize job scheduler
    logger.info('Initializing Scheduler...')
    init_scheduler(app)
    
    # Schedule periodic tasks (run every 24h)
    # Check if we need to run an initial scan (e.g. if any library has no last_scan)
    # OR if TitleDB critical files are missing
    run_now = False
    with app.app_context():
        libs = get_libraries()
        
        # Check for missing TitleDB files
        critical_files = ['cnmts.json', 'versions.json']
        titledb_missing = any(not os.path.exists(os.path.join(TITLEDB_DIR, f)) for f in critical_files)
        
        if not libs or any(l.last_scan is None for l in libs) or titledb_missing:
            run_now = True
            if titledb_missing:
                logger.info("Initial scan required: TitleDB critical files are missing.")
            else:
                logger.info("Initial scan required: New or un-scanned libraries detected.")
    
    app.scheduler.add_job(
        job_id='update_db_and_scan',
        func=update_db_and_scan_job,
        interval=timedelta(hours=24),
        run_first=run_now
    )
    
    # Schedule daily backup at 3 AM
    app.scheduler.add_job(
        job_id='daily_backup',
        func=create_automatic_backup,
        interval=timedelta(days=1),
        run_first=False,
        start_date=datetime.datetime.now().replace(hour=3, minute=0, second=0, microsecond=0)
    )

    log_activity('system_startup', details={'version': BUILD_VERSION})

os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(TITLEDB_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

## Global variables
app_settings = {}
socketio = SocketIO()
limiter = Limiter(key_func=get_remote_address, default_limits=["300 per day", "100 per hour"])
backup_manager = None
# Create a global variable and lock for scan_in_progress
scan_in_progress = False
scan_lock = threading.Lock()
# Global flag for titledb update status
is_titledb_update_running = False
titledb_update_lock = threading.Lock()
plugin_manager = None
cloud_manager = None

# Configure logging
formatter = ColoredFormatter(
    '[%(asctime)s.%(msecs)03d] %(levelname)s (%(module)s) %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)

# Standard logging config
logging.basicConfig(
    level=logging.INFO,
    handlers=[handler]
)

# Structlog configuration
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

# Create main logger (bridged to structlog)
logger = structlog.get_logger('main')

# Apply filter to hide date from http access logs
logging.getLogger('werkzeug').addFilter(FilterRemoveDateFromWerkzeugLogs())

# Suppress specific Alembic INFO logs
logging.getLogger('alembic.runtime.migration').setLevel(logging.WARNING)

def trigger_webhook(event_type, data):
    """Trigger configured webhooks for events"""
    with app.app_context():
        try:
            webhooks = Webhook.query.filter_by(active=True).all()
            for webhook in webhooks:
                # Check if this webhook is interested in this event
                import json
                events = json.loads(webhook.events) if webhook.events else []
                if event_type not in events:
                    continue
                
                payload = {
                    'event': event_type,
                    'timestamp': datetime.datetime.now().isoformat(),
                    'data': data
                }
                
                headers = {'Content-Type': 'application/json'}
                if webhook.secret:
                    signature = hmac.new(
                        webhook.secret.encode(),
                        json.dumps(payload).encode(),
                        hashlib.sha256
                    ).hexdigest()
                    headers['X-MyFoil-Signature'] = signature
                
                try:
                    requests.post(webhook.url, json=payload, headers=headers, timeout=5)
                    logger.debug(f"Webhook {webhook.url} triggered for {event_type}")
                except Exception as e:
                    logger.warning(f"Failed to trigger webhook {webhook.url}: {e}")
        except Exception as e:
            logger.error(f"Error in trigger_webhook: {e}")

@login_manager.user_loader
def load_user(user_id):
    # since the user_id is just the primary key of our user table, use it in the query for the user
    return db.session.get(User, int(user_id))

def reload_conf():
    global app_settings
    global watcher
    app_settings = load_settings()

def on_library_change(events):
    # TODO refactor: group modified and created together
    with app.app_context():
        created_events = [e for e in events if e.type == 'created']
        modified_events = [e for e in events if e.type != 'created']

        for event in modified_events:
            if event.type == 'moved':
                if file_exists_in_db(event.src_path):
                    # update the path
                    update_file_path(event.directory, event.src_path, event.dest_path)
                else:
                    # add to the database
                    event.src_path = event.dest_path
                    created_events.append(event)

            elif event.type == 'deleted':
                # delete the file from library if it exists
                delete_file_by_filepath(event.src_path)

            elif event.type == 'modified':
                # can happen if file copy has started before the app was running
                add_files_to_library(event.directory, [event.src_path])

        if created_events:
            directories = list(set(e.directory for e in created_events))
            for library_path in directories:
                new_files = [e.src_path for e in created_events if e.directory == library_path]
                add_files_to_library(library_path, new_files)
                
                # If Celery is enabled, identify files asynchronously
                if CELERY_ENABLED:
                    for f_path in new_files:
                        identify_file_async.delay(f_path)
                    logger.info(f"Queued async identification for {len(new_files)} files in {library_path}")
                    # Em modo async, não chamar post_library_change aqui
                    # As tarefas Celery irão chamar post_library_change quando completarem
                    return
                else:
                    # Em modo síncrono, processar identificação imediatamente
                    # Mas apenas para arquivos novos, não chamar post_library_change ainda
                    pass

    # Apenas chamar post_library_change se não estiver usando Celery
    # ou se não houver arquivos novos para identificar
    if not CELERY_ENABLED:
        post_library_change()

# Create main blueprint for UI routes
main_bp = Blueprint('main', __name__)

def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = MYFOIL_DB
    app.config['SECRET_KEY'] = get_or_create_secret_key()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    limiter.init_app(app)

    # Initialize I18n
    app.i18n = I18n(app)

    # Register Blueprints
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(main_bp)

    # Initialize REST API (using a blueprint for safety)
    api_bp = Blueprint('api', __name__, url_prefix='/api')
    init_rest_api(api_bp)
    app.register_blueprint(api_bp)

    # Initialize Metrics
    init_metrics(app)

    # Initialize SocketIO with explicit async mode
    socketio.init_app(app, 
        cors_allowed_origins="*", 
        async_mode='eventlet',
        engineio_logger=False, 
        logger=False
    )

    # Global initialization (run even if imported)
    with app.app_context():
        global backup_manager
        backup_manager = BackupManager(CONFIG_DIR, DATA_DIR)
        reload_conf()
        init_db(app)
        init_users(app)
        init_internal(app)
        
        # Initialize Plugins
        global plugin_manager
        plugin_manager = get_plugin_manager(PLUGINS_DIR, app)
        disabled_plugins = app_settings.get('plugins', {}).get('disabled', [])
        plugin_manager.load_plugins(disabled_plugins)
        
        # Initialize Cloud Manager
        global cloud_manager
        cloud_manager = get_cloud_manager(CONFIG_DIR)
        
    if CELERY_ENABLED:
        logger.info("Celery tasks loaded and enabled.")
        
    return app

# Create app factory

@main_bp.context_processor
def inject_version():
    return dict(build_version=BUILD_VERSION)


def tinfoil_error(error):
    return jsonify({
        'error': error
    })

def tinfoil_access(f):
    @wraps(f)
    def _tinfoil_access(*args, **kwargs):
        reload_conf()
        hauth_success = None
        auth_success = None
        request.verified_host = None
        # Host verification to prevent hotlinking
        #Tinfoil doesn't send Hauth for file grabs, only directories, so ignore get_game endpoints.
        host_verification = "/api/get_game" not in request.path and (request.is_secure or request.headers.get("X-Forwarded-Proto") == "https")
        if host_verification:
            request_host = request.host
            request_hauth = request.headers.get('Hauth')
            logger.info(f"Secure Tinfoil request from remote host {request_host}, proceeding with host verification.")
            shop_host = app_settings["shop"].get("host")
            shop_hauth = app_settings["shop"].get("hauth")
            if not shop_host:
                logger.error("Missing shop host configuration, Host verification is disabled.")

            elif request_host != shop_host:
                logger.warning(f"Incorrect URL referrer detected: {request_host}.")
                error = f"Incorrect URL `{request_host}`."
                hauth_success = False

            elif not shop_hauth:
                # Try authentication, if an admin user is logging in then set the hauth
                auth_success, auth_error, auth_is_admin =  basic_auth(request)
                if auth_success and auth_is_admin:
                    shop_settings = app_settings['shop']
                    shop_settings['hauth'] = request_hauth
                    set_shop_settings(shop_settings)
                    logger.info(f"Successfully set Hauth value for host {request_host}.")
                    hauth_success = True
                else:
                    logger.warning(f"Hauth value not set for host {request_host}, Host verification is disabled. Connect to the shop from Tinfoil with an admin account to set it.")

            elif request_hauth != shop_hauth:
                logger.warning(f"Incorrect Hauth detected for host: {request_host}.")
                error = f"Incorrect Hauth for URL `{request_host}`."
                hauth_success = False

            else:
                hauth_success = True
                request.verified_host = shop_host

            if hauth_success is False:
                return tinfoil_error(error)
        
        # Now checking auth if shop is private
        if not app_settings['shop']['public']:
            # Shop is private
            if auth_success is None:
                # First check if user is logged in via session (Browser)
                if current_user.is_authenticated and current_user.has_access('shop'):
                    auth_success = True
                else:
                    # Fallback to Basic Auth (Tinfoil)
                    auth_success, auth_error, _ = basic_auth(request)
            
            if not auth_success:
                return tinfoil_error(auth_error)
        # Auth success
        return f(*args, **kwargs)
    return _tinfoil_access

def access_shop():
    return render_template('index.html', title='Library', 
                           admin_account_created=admin_account_created(), 
                           valid_keys=app_settings['titles']['valid_keys'],
                           total_files=Files.query.count(),
                           games=None)


@access_required('shop')
def access_shop_auth():
    return access_shop()

@main_bp.route('/')
def index():

    @tinfoil_access
    def access_tinfoil_shop():
        shop = {
            "success": app_settings['shop']['motd']
        }
        
        if request.verified_host is not None:
            # enforce client side host verification
            shop["referrer"] = f"https://{request.verified_host}"
            
        files_list, titles_map = gen_shop_files(db)
        shop["files"] = files_list
        shop["titles"] = titles_map

        if app_settings['shop']['encrypt']:
            return Response(encrypt_shop(shop), mimetype='application/octet-stream')

        return jsonify(shop)
    
    if all(header in request.headers for header in TINFOIL_HEADERS):
    # if True:
        logger.info(f"Tinfoil connection from {request.remote_addr}")
        return access_tinfoil_shop()
    
    if not app_settings['shop']['public']:
        return access_shop_auth()
    return access_shop()

@main_bp.route('/api/docs')
def api_docs_redirect():
    return redirect('/api/docs/')

@main_bp.route('/stats')
@access_required('shop')
def stats_page():
    return render_template('stats.html', title='Statistics')

@main_bp.route('/settings')
@access_required('admin')
def settings_page():
    languages = {}
    try:
        languages_path = os.path.join(TITLEDB_DIR, 'languages.json')
        if os.path.exists(languages_path):
            with open(languages_path) as f:
                languages = json.load(f)
                languages = dict(sorted(languages.items()))
    except Exception as e:
        logger.warning(f"Could not load languages.json: {e}")

    return render_template(
        'settings.html',
        title='Settings',
        languages_from_titledb=languages,
        admin_account_created=admin_account_created(),
        valid_keys=app_settings['titles']['valid_keys'],
        active_source=titledb.get_active_source_info())

@main_bp.route('/api/settings')
@access_required('admin')
def get_settings_api():
    reload_conf()
    settings = copy.deepcopy(app_settings)
    
    # Flatten settings for the JS frontend
    flattened = {}
    for section, values in settings.items():
        if isinstance(values, dict):
            for key, value in values.items():
                flattened[f"{section}/{key}"] = value
        else:
            flattened[section] = values

    # Tinfoil Auth specific handling
    if settings.get('shop', {}).get('hauth'):
        flattened['shop/hauth'] = True
    else:
        flattened['shop/hauth'] = False
        
    return jsonify(flattened)

@main_bp.post('/api/settings/titles')
@access_required('admin')
def set_titles_settings_api():
    settings = request.json
    current_settings = load_settings()
    
    region = settings.get('region', current_settings['titles'].get('region', 'US'))
    language = settings.get('language', current_settings['titles'].get('language', 'en'))
    dbi_versions = settings.get('dbi_versions', current_settings['titles'].get('dbi_versions', False))
    
    languages_path = os.path.join(TITLEDB_DIR, 'languages.json')
    if os.path.exists(languages_path):
        with open(languages_path) as f:
            languages = json.load(f)
            languages = dict(sorted(languages.items()))

        if region not in languages or language not in languages[region]:
            resp = {
                'success': False,
                'errors': [{
                        'path': 'titles',
                        'error': f"The region/language pair {region}/{language} is not available."
                    }]
            }
            return jsonify(resp)
    
    set_titles_settings(region, language, dbi_versions)
    reload_conf()
    
    # Run update in background
    threading.Thread(target=update_titledb_job, args=(True,)).start()
    
    resp = {
        'success': True,
        'errors': []
    }
    return jsonify(resp)

@main_bp.route('/api/settings/regions')
@access_required('admin')
def get_regions_api():
    languages_path = os.path.join(TITLEDB_DIR, 'languages.json')
    if not os.path.exists(languages_path):
        return jsonify({'regions': []})
    try:
        with open(languages_path) as f:
            languages = json.load(f)
        return jsonify({'regions': sorted(list(languages.keys()))})
    except:
        return jsonify({'regions': []})

@main_bp.route('/api/settings/languages')
@access_required('admin')
def get_languages_api():
    languages_path = os.path.join(TITLEDB_DIR, 'languages.json')
    if not os.path.exists(languages_path):
        return jsonify({'languages': []})
    try:
        with open(languages_path) as f:
            languages = json.load(f)
        all_langs = set()
        for region_langs in languages.values():
            all_langs.update(region_langs)
        return jsonify({'languages': sorted(list(all_langs))})
    except:
        return jsonify({'languages': []})

@main_bp.route('/api/settings/renaming', methods=['GET', 'POST'])
@access_required('admin')
def renaming_settings_api():
    if request.method == 'POST':
        data = request.json
        settings = load_settings()
        if 'renaming' not in settings:
            settings['renaming'] = {}
        
        settings['renaming']['enabled'] = data.get('enabled', False)
        settings['renaming']['pattern_base'] = data.get('pattern_base', '{Name} [{TitleID}] [v{Version}]')
        settings['renaming']['pattern_upd'] = data.get('pattern_upd', '{Name} [UPD] [{TitleID}] [v{Version}]')
        settings['renaming']['pattern_dlc'] = data.get('pattern_dlc', '{Name} [DLC] [{TitleID}] [v{Version}]')
        
        with open(CONFIG_FILE, 'w') as yaml_file:
            yaml.dump(settings, yaml_file)
        reload_conf()
        
        return jsonify({'success': True})
    
    settings = load_settings()
    renaming = settings.get('renaming', DEFAULT_SETTINGS['renaming'])
    return jsonify({'success': True, 'settings': renaming})

@main_bp.post('/api/renaming/preview')
@access_required('admin')
def preview_renaming_api():
    data = request.json
    patterns = {
        'BASE': data.get('pattern_base'),
        'UPDATE': data.get('pattern_upd'), # APP_TYPE_UPD constant is 'UPDATE'
        'DLC': data.get('pattern_dlc')
    }
    
    from renamer import get_file_metadata, sanitize_filename
    
    # Get a sample file for each type
    results = []
    types_to_find = ['BASE', 'UPDATE', 'DLC']
    
    for app_type in types_to_find:
        # Find a file of this type
        # Join Files -> Apps where app_type matches
        sample_file = db.session.query(Files).join(Files.apps).filter(Apps.app_type == app_type).first()
        
        if sample_file:
            meta = get_file_metadata(sample_file.id)
            if meta:
                pattern = patterns.get(app_type)
                new_name = pattern
                for key, value in meta.items():
                    new_name = new_name.replace(f"{{{key}}}", str(value))
                new_name = sanitize_filename(new_name) + f".{meta['Ext']}"
                
                results.append({
                    'type': app_type,
                    'original': sample_file.filename,
                    'new': new_name
                })
    
    return jsonify({'success': True, 'preview': results})

@main_bp.post('/api/renaming/run')
@access_required('admin')
def run_renaming_api():
    settings = load_settings()
    renaming_cfg = settings.get('renaming', DEFAULT_SETTINGS['renaming'])
    
    patterns = {
        'BASE': renaming_cfg.get('pattern_base'),
        'UPDATE': renaming_cfg.get('pattern_upd'),
        'DLC': renaming_cfg.get('pattern_dlc')
    }
    
    from renamer import start_renaming_job
    
    # Run in background to avoid timeout
    def run_wrapper():
        with app.app_context():
            start_renaming_job(patterns)
            
    threading.Thread(target=run_wrapper).start()
    
    return jsonify({'success': True, 'message': 'Renaming job started in background'})

@main_bp.post('/api/settings/shop')
def set_shop_settings_api():
    data = request.json
    set_shop_settings(data)
    reload_conf()
    resp = {
        'success': True,
        'errors': []
    } 
    return jsonify(resp)

@main_bp.route('/api/settings/library/paths', methods=['GET', 'POST', 'DELETE'])
@access_required('admin')
def library_paths_api():
    global watcher
    if request.method == 'POST':
        data = request.json
        success, errors = add_library_complete(app, watcher, data['path'])
        if success:
            reload_conf()
            post_library_change()
        resp = {
            'success': success,
            'errors': errors
        }
    elif request.method == 'GET':
        reload_conf()
        libs = Libraries.query.all()
        paths_info = []
        for l in libs:
            # Files in this library
            files_count = Files.query.filter_by(library_id=l.id).count()
            total_size = db.session.query(func.sum(Files.size)).filter_by(library_id=l.id).scalar() or 0
            
            # Identified titles (approximate by distinct apps)
            # We join to get title_id from Apps linked to files in this library
            try:
                titles_query = db.session.query(Apps.title_id).distinct().join(app_files).join(Files).filter(Files.library_id == l.id)
                titles_count = titles_query.count()
            except Exception as e:
                logger.error(f"Error counting titles for path {l.path}: {e}")
                titles_count = 0
            
            paths_info.append({
                'id': l.id,
                'path': l.path,
                'files_count': files_count,
                'total_size': total_size,
                'total_size_formatted': format_size_py(total_size),
                'titles_count': titles_count,
                'last_scan': l.last_scan.strftime("%Y-%m-%d %H:%M:%S") if l.last_scan else "Nunca"
            })
        
        resp = {
            'success': True,
            'errors': [],
            'paths': paths_info
        }
    elif request.method == 'DELETE':
        data = request.json
        success, errors = remove_library_complete(app, watcher, data['path'])
        if success:
            reload_conf()
            post_library_change()
        resp = {
            'success': success,
            'errors': errors
        }
    return jsonify(resp)

@main_bp.post('/api/settings/keys')
@access_required('admin')
def set_keys_api():
    errors = []
    success = False

    file = request.files['file']
    if file and allowed_file(file.filename):
        # filename = secure_filename(file.filename)
        file.save(KEYS_FILE + '.tmp')
        logger.info(f'Validating {file.filename}...')
        valid = load_keys(KEYS_FILE + '.tmp')
        if valid:
            os.rename(KEYS_FILE + '.tmp', KEYS_FILE)
            success = True
            logger.info('Successfully saved valid keys.txt')
            reload_conf()
            post_library_change()
        else:
            os.remove(KEYS_FILE + '.tmp')
            logger.error(f'Invalid keys from {file.filename}')

    resp = {
        'success': success,
        'errors': errors
    } 
    return jsonify(resp)


@main_bp.route('/api/settings/titledb/sources', methods=['GET', 'POST', 'PUT', 'DELETE'])
@access_required('admin')
def titledb_sources_api():
    """Manage TitleDB sources"""
    if request.method == 'GET':
        # Get all sources and their status
        sources = titledb.get_titledb_sources_status()
        return jsonify({
            'success': True,
            'sources': sources
        })
    
    elif request.method == 'POST':
        # Add a new source
        data = request.json
        name = data.get('name')
        base_url = data.get('base_url')
        priority = data.get('priority', 50)
        enabled = data.get('enabled', True)
        source_type = data.get('source_type', 'json')
        
        if not name or not base_url:
            return jsonify({
                'success': False,
                'errors': ['Name and base_url are required']
            })
        
        success = titledb.add_titledb_source(name, base_url, priority, enabled, source_type)
        return jsonify({
            'success': success,
            'errors': [] if success else ['Failed to add source']
        })
    
    elif request.method == 'PUT':
        # Update an existing source
        data = request.json
        name = data.get('name')
        
        if not name:
            return jsonify({
                'success': False,
                'errors': ['Name is required']
            })
        
        # Build kwargs for update
        kwargs = {}
        if 'base_url' in data:
            kwargs['base_url'] = data['base_url']
        if 'priority' in data:
            kwargs['priority'] = data['priority']
        if 'enabled' in data:
            kwargs['enabled'] = data['enabled']
        if 'source_type' in data:
            kwargs['source_type'] = data['source_type']
        
        success = titledb.update_titledb_source(name, **kwargs)
        return jsonify({
            'success': success,
            'errors': [] if success else ['Failed to update source']
        })
    
    elif request.method == 'DELETE':
        # Remove a source
        data = request.json
        name = data.get('name')
        
        if not name:
            return jsonify({
                'success': False,
                'errors': ['Name is required']
            })
        
        success = titledb.remove_titledb_source(name)
        return jsonify({
            'success': success,
            'errors': [] if success else ['Failed to remove source']
        })




@main_bp.post('/api/settings/titledb/sources/reorder')
@access_required('admin')
def titledb_sources_reorder_api():
    """Update TitleDB source priorities"""
    data = request.json
    if not data:
        return jsonify({'success': False, 'errors': ['No data provided']})
    
    success = titledb.update_titledb_priorities(data)
    return jsonify({
        'success': success,
        'errors': [] if success else ['Failed to update priorities']
    })

@main_bp.post('/api/settings/titledb/sources/refresh-dates')
@access_required('admin')
def refresh_titledb_sources_dates_api():
    """Trigger background refresh of remote dates"""
    titledb.refresh_titledb_remote_dates()
    return jsonify({'success': True})

@main_bp.post('/api/settings/titledb/update')
@access_required('admin')
def force_titledb_update_api():
    """Force a TitleDB update in background"""
    threading.Thread(target=update_titledb_job, args=(True,)).start()
    return jsonify({
        'success': True,
        'message': 'Update started in background'
    })


@main_bp.route('/api/titles', methods=['GET'])
@access_required('shop')
def get_all_titles_api():
    titles_library = generate_library()

    return jsonify({
        'total': len(titles_library),
        'games': titles_library
    })

@main_bp.route('/api/set_language/<lang>', methods=['POST'])
def set_language(lang):
    if lang in ['en', 'pt_BR']:
        resp = jsonify({'success': True})
        # Set cookie for 1 year
        resp.set_cookie('language', lang, max_age=31536000)
        return resp
    return jsonify({'success': False, 'error': 'Invalid language'}), 400

@main_bp.route('/api/get_game/<int:id>')
@tinfoil_access
def serve_game(id):
    # TODO add download count increment
    file = Files.query.get(id)
    if not file:
        return "File not found", 404
    filedir, filename = os.path.split(file.filepath)
    return send_from_directory(filedir, filename)

@main_bp.route('/api/app_info/<id>')
@access_required('shop')
def app_info_api(id):
    # Try to get by TitleID first (hex string)
    tid = str(id).upper()
    title_obj = Titles.query.filter_by(title_id=tid).first()
    
    # If not found by TitleID, try by integer primary key (legacy/fallback)
    app_obj = None
    if not title_obj and str(id).isdigit():
        app_obj = db.session.get(Apps, int(id))
        if app_obj:
            tid = app_obj.title.title_id
            title_obj = app_obj.title

    is_dlc_request = False
    if not title_obj:
        # Maybe it's a DLC app_id, try to find base TitleID
        titles_lib.load_titledb() # Ensure loaded
        base_tid, app_type = titles_lib.identify_appId(tid)
        if base_tid and tid != base_tid:
             # It's a DLC or Update. 
             # For the main game modal, we usually want the base_tid.
             # But let's check if we should stay on this ID
             if app_type == APP_TYPE_DLC:
                 is_dlc_request = True
             else:
                 tid = base_tid
                 title_obj = Titles.query.filter_by(title_id=tid).first()
    
    # If still not found, we can't show much, but let's try to show TitleDB info
    # if it's a valid TitleID even if not in our DB
    
    # Get basic info from titledb
    info = titles_lib.get_game_info(tid)
    if not info:
        info = {
            'name': f'Unknown ({tid})',
            'publisher': '--',
            'description': 'No information available.',
            'release_date': '--',
            'iconUrl': '/static/img/no-icon.png'
        }
    
    if not title_obj:
        # Game/Title not in our database as a main Title, or specifically a DLC request
        result = info.copy()
        result['id'] = tid
        result['app_id'] = tid
        result['owned_version'] = 0
        result['has_base'] = False
        result['has_latest_version'] = False
        result['has_all_dlcs'] = False
        result['owned'] = False
        
        # Files for this specific DLC if owned
        dlc_files = []
        app_obj_dlc = Apps.query.filter_by(app_id=tid, owned=True).first()
        if app_obj_dlc:
            result['owned'] = True
            for f in app_obj_dlc.files:
                dlc_files.append({
                    'id': f.id,
                    'filename': f.filename,
                    'filepath': f.filepath,
                    'size_formatted': format_size_py(f.size)
                })
        
        result['files'] = dlc_files
        result['updates'] = []
        result['dlcs'] = []
        result['category'] = info.get('category', [])
        return jsonify(result)
    
    # Get all apps for this title
    all_title_apps = get_all_title_apps(tid)
    
    # Base Files (from owned BASE apps)
    base_files = []
    base_apps = [a for a in all_title_apps if a['app_type'] == APP_TYPE_BASE and a['owned']]
    for b in base_apps:
        # We need the original Files objects to get IDs for download
        app_model = db.session.get(Apps, b['id'])
        for f in app_model.files:
            base_files.append({
                'id': f.id,
                'filename': f.filename,
                'filepath': f.filepath,
                'size': f.size,
                'size_formatted': format_size_py(f.size),
                'version': app_model.app_version
            })
    
    # Deduplicate files by ID
    seen_ids = set()
    unique_base_files = []
    seen_file_ids_in_modal = set()
    for f in base_files:
        if f['id'] not in seen_ids:
            unique_base_files.append(f)
            seen_ids.add(f['id'])
            seen_file_ids_in_modal.add(f['id'])

    # Updates and DLCs (for detailed listing)
    available_versions = titles_lib.get_all_existing_versions(tid)
    version_release_dates = {v['version']: v['release_date'] for v in available_versions}
    
    # Ensure v0 has the base game release date in YYYY-MM-DD format
    base_release_date = info.get('release_date', '')
    if base_release_date and len(str(base_release_date)) == 8 and str(base_release_date).isdigit():
        # Format YYYYMMDD to YYYY-MM-DD
        formatted_date = f"{str(base_release_date)[:4]}-{str(base_release_date)[4:6]}-{str(base_release_date)[6:]}"
        # Update info for the main response
        info['release_date'] = formatted_date
        # Set for v0
        version_release_dates[0] = formatted_date
    elif base_release_date:
        version_release_dates[0] = base_release_date


    update_apps = [a for a in all_title_apps if a['app_type'] == APP_TYPE_UPD]
    updates_list = []
    for upd in update_apps:
        v_int = int(upd['app_version'])
        if v_int == 0: continue # Skip base version in updates history
        
        # Get file IDs for owned updates
        files = []
        if upd['owned']:
            app_model = db.session.get(Apps, upd['id'])
            for f in app_model.files:
                if f.id in seen_file_ids_in_modal:
                    continue
                files.append({'id': f.id, 'filename': f.filename, 'size_formatted': format_size_py(f.size)})
        
        updates_list.append({
            'version': v_int,
            'owned': upd['owned'],
            'release_date': version_release_dates.get(v_int, 'Unknown'),
            'files': files
        })
    
    # DLCs
    dlc_ids = titles_lib.get_all_existing_dlc(tid)
    dlcs_list = []
    dlc_apps_grouped = {}
    for a in [a for a in all_title_apps if a['app_type'] == APP_TYPE_DLC]:
        aid = a['app_id']
        if aid not in dlc_apps_grouped: dlc_apps_grouped[aid] = []
        dlc_apps_grouped[aid].append(a)
        
    for dlc_id in dlc_ids:
        apps_for_dlc = dlc_apps_grouped.get(dlc_id, [])
        owned = any(a['owned'] for a in apps_for_dlc)
        files = []
        if owned:
            for a in apps_for_dlc:
                if a['owned']:
                    app_model = db.session.get(Apps, a['id'])
                    for f in app_model.files:
                        files.append({
                            'id': f.id, 
                            'filename': f.filename, 
                            'filepath': f.filepath,
                            'size_formatted': format_size_py(f.size)
                        })
        
        dlc_info = titles_lib.get_game_info(dlc_id)
        dlcs_list.append({
            'app_id': dlc_id,
            'name': dlc_info.get('name', f'DLC {dlc_id}'),
            'owned': owned,
            'release_date': dlc_info.get('release_date', ''),
            'files': files # Includes filename and id, let's ensure filepath is there too if needed
        })

    result = info.copy()
    result['id'] = tid
    result['app_id'] = tid
    result['title_id'] = tid
    
    # Calculate corrected owned version considering all owned apps (Base + Update)
    owned_versions = [int(a['app_version']) for a in all_title_apps if a['owned']]
    result['owned_version'] = max(owned_versions) if owned_versions else 0
    result['display_version'] = result['owned_version']
    
    # Use status from title_obj (re-calculated with corrected logic in library.py/update_titles)
    result['has_base'] = title_obj.have_base
    result['has_latest_version'] = title_obj.up_to_date
    result['has_all_dlcs'] = title_obj.complete
    
    result['files'] = unique_base_files
    result['updates'] = sorted(updates_list, key=lambda x: x['version'])
    result['dlcs'] = sorted(dlcs_list, key=lambda x: x['name'])
    result['category'] = info.get('category', []) # Genre/Categories

    # Total size for side info
    total_size = 0
    for a in all_title_apps:
        if a['owned']:
            app_model = db.session.get(Apps, a['id'])
            for f in app_model.files:
                total_size += f.size
    
    result['size'] = total_size
    result['size_formatted'] = format_size_py(total_size)
    
    # Calculate status_color consistent with library list
    if result['has_base'] and (not result['has_latest_version'] or not result['has_all_dlcs']):
        result['status_color'] = 'orange'
    elif result['has_base']:
         result['status_color'] = 'green'
    else:
         result['status_color'] = 'gray'

    return jsonify(result)

@main_bp.route('/api/files/unidentified')
@access_required('admin')
def get_unidentified_files_api():
    import titles
    # 1. Arquivos sem TitleID (Falha técnica de identificação)
    files = get_all_unidentified_files()
    results = [{
        'id': f.id,
        'filename': f.filename,
        'filepath': f.filepath,
        'size': f.size,
        'size_formatted': format_size_py(f.size),
        'error': f.identification_error or 'Arquivo não identificado (ID ausente)'
    } for f in files]
    
    # 2. Arquivos com TitleID mas sem reconhecimento de nome (Unknown)
    # Buscamos por arquivos que pertencem a jogos "Unknown" no TitleDB
    identified_files = Files.query.filter_by(identified=True).all()
    for f in identified_files:
        if not f.apps:
            continue
            
        # Pega o primeiro app associado (normalmente arquivos NSP/XCI pertencem a 1 app)
        try:
            tid = f.apps[0].title.title_id
            tinfo = titles.get_title_info(tid)
            name = tinfo.get('name', '')
            
            # Se for desconhecido (começa com Unknown ou vazio)
            if not name or name.startswith('Unknown'):
                results.append({
                    'id': f.id,
                    'filename': f.filename,
                    'filepath': f.filepath,
                    'size': f.size,
                    'size_formatted': format_size_py(f.size),
                    'error': f'Título não reconhecido no Banco de Dados ({tid})'
                })
        except (IndexError, AttributeError):
            continue
            
    return jsonify(results)

@main_bp.route('/api/files/delete/<int:file_id>', methods=['POST'])
@access_required('admin')
def delete_file_api(file_id):
    try:
        # Find associated TitleID before deletion for cache update
        file_obj = db.session.get(Files, file_id)
        if not file_obj:
            return jsonify({'success': False, 'error': 'File not found'}), 404
            
        title_ids = []
        if file_obj.apps:
            title_ids = list(set([a.title.title_id for a in file_obj.apps if a.title]))

        success, error = delete_file_from_db_and_disk(file_id)
        
        if success:
            logger.info(f"File {file_id} deleted. Updating cache for titles: {title_ids}")
            for tid in title_ids:
                try:
                    library_lib.update_game_in_cache(tid)
                except Exception as ex:
                    logger.error(f"Error updating cache for title {tid}: {ex}")
        else:
            logger.warning(f"File deletion failed for {file_id}: {error}")
                
        return jsonify({'success': success, 'error': error})
    except Exception as e:
        logger.exception(f"Unhandled error in delete_file_api: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500



@debounce(10)
def post_library_change():
    with app.app_context():
        titles.load_titledb()
        process_library_identification(app)
        add_missing_apps_to_db()
        update_titles() # Ensure titles are updated after identification
        # remove missing files
        remove_missing_files_from_db()
        # The process_library_identification already handles updating titles and generating library
        # So, we just need to ensure titles_library is updated from the generated library
        generate_library(force=True)
        titles.identification_in_progress_count -= 1
        titles.unload_titledb()
        
        # Notify clients about the change
        socketio.emit('library_updated', {'timestamp': datetime.datetime.now().isoformat()}, namespace='/')
        trigger_webhook('library_updated', {'timestamp': datetime.datetime.now().isoformat()})
        
        # Plugin Hook
        if plugin_manager:
            plugin_manager.trigger_event('library_updated', {'timestamp': datetime.datetime.now().isoformat()})

@main_bp.post('/api/library/scan')
@access_required('admin')
def scan_library_api():
    data = request.json
    path = data['path']
    success = True
    errors = []

    global scan_in_progress
    with scan_lock:
        if scan_in_progress:
            logger.info('Skipping scan_library_api call: Scan already in progress')
            return {'success': False, 'errors': []}
    # Set the scan status to in progress
    scan_in_progress = True

    try:
        if CELERY_ENABLED:
            if path is None:
                scan_all_libraries_async.delay()
                logger.info("Triggered asynchronous full library scan.")
            else:
                scan_library_async.delay(path)
                logger.info(f"Triggered asynchronous library scan for: {path}")
            return jsonify({'success': True, 'async': True, 'errors': []})
        else:
            if path is None:
                scan_library()
            else:
                scan_library_path(path)
            post_library_change()
            return jsonify({'success': True, 'async': False, 'errors': []})
    except Exception as e:
        errors.append(str(e))
        success = False
        logger.error(f"Error during library scan: {e}")
    finally:
        if not CELERY_ENABLED:
            with scan_lock:
                scan_in_progress = False
    resp = {
        'success': success,
        'errors': errors
    } 
    return jsonify(resp)

@main_bp.route('/api/system/info')
@access_required('shop')
def system_info_api():
    from settings import load_settings
    settings = load_settings()
    
    # Get detailed source info
    source_info = titledb.get_active_source_info()
    source_name = source_info.get('name', 'TitleDB') if source_info else 'TitleDB'
    
    titledb_file = titles.get_loaded_titles_file()
    
    # Check what update source we are using
    update_src = "TitleDB (versions.json)"
    
    # Identification source - show Source Name + Region File
    if titledb_file != "None":
        id_src = f"{source_name} ({titledb_file})"
    else:
        id_src = f"{source_name} (Não carregado)"
    
    return jsonify({
        'build_version': BUILD_VERSION,
        'id_source': id_src,
        'update_source': update_src,
        'titledb_region': settings.get('titles/region', 'US'),
        'titledb_language': settings.get('titles/language', 'en'),
        'titledb_file': titledb_file
    })

def scan_library():
    logger.info(f'Scanning whole library ...')
    libraries = get_libraries()
    for library in libraries:
        scan_library_path(library.path) # Only scan, identification will be done globally

@main_bp.route('/api/library')
@access_required('shop')
def library_api():
    # Fast check for cache and ETag
    cached = load_library_from_disk()
    if cached and 'hash' in cached:
        etag = cached['hash']
        if request.headers.get('If-None-Match') == etag:
            return '', 304
    
    # Paginação: obter parâmetros da query string
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    
    # Validar parâmetros
    page = max(1, page)  # Página mínima é 1
    per_page = min(max(1, per_page), 500)  # Entre 1 e 500 itens por página
    
    # generate_library will use cache if force=False (default)
    lib_data = generate_library()
    total_items = len(lib_data)
    
    # Calcular paginação
    total_pages = (total_items + per_page - 1) // per_page  # Ceiling division
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    # Aplicar paginação
    paginated_data = lib_data[start_idx:end_idx]
    
    # We need the hash for the header, so we reload from disk to get the full dict
    full_cache = load_library_from_disk()
    
    # Preparar resposta com metadados de paginação
    response_data = {
        'items': paginated_data,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total_items': total_items,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1
        }
    }
    
    resp = jsonify(response_data)
    if full_cache and 'hash' in full_cache:
        resp.set_etag(full_cache['hash'])
        # Adicionar headers de paginação
        resp.headers['X-Total-Count'] = str(total_items)
        resp.headers['X-Page'] = str(page)
        resp.headers['X-Per-Page'] = str(per_page)
        resp.headers['X-Total-Pages'] = str(total_pages)
    return resp

@main_bp.route('/api/library/search')
@access_required('shop')
def search_library_api():
    query = request.args.get('q', '').lower()
    genre = request.args.get('genre')
    owned_only = request.args.get('owned') == 'true'
    missing_only = request.args.get('missing') == 'true'
    up_to_date = request.args.get('up_to_date') == 'true'
    pending = request.args.get('pending') == 'true'
    
    lib_data = generate_library()
    
    results = []
    for game in lib_data:
        # Text search
        if query:
            name = (game.get('name') or '').lower()
            publisher = (game.get('publisher') or '').lower()
            tid = (game.get('id') or '').lower()
            if query not in name and query not in publisher and query not in tid:
                continue
        
        # Genre filter
        if genre and genre != 'Todos os Gêneros':
            categories = game.get('category') or []
            if genre not in categories:
                continue
        
        # Ownership filters
        is_owned = game.get('have_base', False)
        if owned_only and not is_owned:
            continue
        if missing_only and is_owned:
            continue
            
        # Status filters
        is_up_to_date = game.get('up_to_date', False)
        if up_to_date and not is_up_to_date:
            continue
        
        has_pending = not is_up_to_date and is_owned
        if pending and not has_pending:
            continue
            
        results.append(game)
    
    return jsonify({
        'count': len(results),
        'results': results[:100] # Limit to 100 for performance
    })

@main_bp.route('/api/settings/webhooks')
@access_required('admin')
def get_webhooks_api():
    webhooks = Webhook.query.all()
    return jsonify([w.to_dict() for w in webhooks])

@main_bp.post('/api/settings/webhooks')
@access_required('admin')
def add_webhook_api():
    data = request.json
    import json
    webhook = Webhook(
        url=data['url'],
        events=json.dumps(data.get('events', ['library_updated'])),
        secret=data.get('secret'),
        active=data.get('active', True)
    )
    db.session.add(webhook)
    db.session.commit()
    return jsonify({'success': True, 'webhook': webhook.to_dict()})

@main_bp.delete('/api/settings/webhooks/<int:id>')
@access_required('admin')
def delete_webhook_api(id):
    webhook = db.session.get(Webhook, id)
    if webhook:
        db.session.delete(webhook)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Webhook not found'}), 404

@main_bp.route('/api/titledb/search')
@access_required('shop')
def search_titledb_api():
    query = request.args.get('q', '').lower()
    if not query or len(query) < 2:
        return jsonify([])
        
    results = titles.search_titledb_by_name(query)
    return jsonify(results[:20]) # Limit to 20 results

@main_bp.route('/api/games/<tid>/custom', methods=['GET'])
@access_required('shop')
def get_game_custom_info(tid):
    info = titles.get_custom_title_info(tid)
    return jsonify({'success': True, 'data': info})

@main_bp.route('/api/games/<tid>/custom', methods=['POST'])
@access_required('shop') # OR admin? shop usually implies user write access in this context
def update_game_custom_info(tid):
    data = request.json
    success, error = titles.save_custom_title_info(tid, data)
    
    if success:
        # Invalidate library cache so the new info appears immediately
        invalidate_library_cache()
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': error}), 500

@main_bp.route('/api/status')
@limiter.exempt
def process_status_api():
    return jsonify({
        'scanning': scan_in_progress,
        'updating_titledb': is_titledb_update_running
    })

@main_bp.post('/api/backup/create')
@access_required('admin')
def create_backup_api():
    """Create a manual backup"""
    global backup_manager
    if not backup_manager:
        return jsonify({'success': False, 'error': 'Backup manager not initialized'}), 500
    
    success, timestamp = backup_manager.create_backup()
    if success:
        return jsonify({
            'success': True,
            'timestamp': timestamp,
            'message': 'Backup created successfully'
        })
    else:
        return jsonify({'success': False, 'error': 'Backup failed'}), 500

@main_bp.get('/api/backup/list')
@access_required('admin')
def list_backups_api():
    """List all available backups"""
    global backup_manager
    if not backup_manager:
        return jsonify({'success': False, 'error': 'Backup manager not initialized'}), 500
    
    backups = backup_manager.list_backups()
    return jsonify({
        'success': True,
        'backups': backups
    })

@main_bp.post('/api/backup/restore')
@access_required('admin')
def restore_backup_api():
    """Restore from a backup"""
    global backup_manager
    if not backup_manager:
        return jsonify({'success': False, 'error': 'Backup manager not initialized'}), 500
    
    data = request.json
    filename = data.get('filename')
    
    if not filename:
        return jsonify({'success': False, 'error': 'Filename required'}), 400
    
    success = backup_manager.restore_backup(filename)
    if success:
        return jsonify({
            'success': True,
            'message': f'Restored from {filename}. Please restart the application.'
        })
    else:
        return jsonify({'success': False, 'error': 'Restore failed'}), 500

# --- Stats Dashboard APIs (4.3.x) ---

@main_bp.route('/api/stats/overview')
@access_required('shop')
def get_stats_overview():
    """Estatísticas detalhadas da biblioteca com filtros - Otimizado"""
    import titles
    import library
    
    library_id = request.args.get('library_id', type=int)
    
    # 1. Fetch library list for filter dropdown
    libs = Libraries.query.all()
    libraries_list = [{'id': l.id, 'path': l.path} for l in libs]

    # 2. Otimização: Combinar todas as queries de Files em uma única query com agregações
    if library_id:
        # Query otimizada usando join direto ao invés de subquery
        file_stats = db.session.query(
            func.count(Files.id).label('total_files'),
            func.sum(Files.size).label('total_size'),
            func.sum(case((Files.identified == False, 1), else_=0)).label('unidentified_files')
        ).filter(Files.library_id == library_id).first()
        
        # Query otimizada para Apps usando join direto (não usado diretamente, mas mantido para compatibilidade)
        apps_query = Apps.query.join(app_files).join(Files).filter(Files.library_id == library_id)
    else:
        # Query otimizada sem filtro de library
        file_stats = db.session.query(
            func.count(Files.id).label('total_files'),
            func.sum(Files.size).label('total_size'),
            func.sum(case((Files.identified == False, 1), else_=0)).label('unidentified_files')
        ).first()
        
        apps_query = Apps.query

    # Extrair resultados da query otimizada
    total_files = file_stats.total_files or 0
    total_size = file_stats.total_size or 0
    unidentified_files = file_stats.unidentified_files or 0
    identified_files = total_files - unidentified_files
    id_rate = round((identified_files / total_files * 100), 1) if total_files > 0 else 0

    # 4. Collection Breakdown (Owned Apps) - Otimizado com uma única query
    # Combinar todas as contagens em uma única query usando agregações condicionais
    if library_id:
        owned_apps_stats = db.session.query(
            func.sum(case((Apps.owned == True, 1), else_=0)).label('total_owned'),
            func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_BASE), 1), else_=0)).label('total_bases'),
            func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_UPD), 1), else_=0)).label('total_updates'),
            func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_DLC), 1), else_=0)).label('total_dlcs'),
            func.count(func.distinct(case((Apps.owned == True, Apps.title_id), else_=None))).label('distinct_titles')
        ).select_from(Apps).join(app_files).join(Files).filter(Files.library_id == library_id).first()
    else:
        owned_apps_stats = db.session.query(
            func.sum(case((Apps.owned == True, 1), else_=0)).label('total_owned'),
            func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_BASE), 1), else_=0)).label('total_bases'),
            func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_UPD), 1), else_=0)).label('total_updates'),
            func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_DLC), 1), else_=0)).label('total_dlcs'),
            func.count(func.distinct(case((Apps.owned == True, Apps.title_id), else_=None))).label('distinct_titles')
        ).select_from(Apps).first()
    
    total_owned_bases = owned_apps_stats.total_bases or 0
    total_owned_updates = owned_apps_stats.total_updates or 0
    total_owned_dlcs = owned_apps_stats.total_dlcs or 0
    total_owned_distinct_titles = owned_apps_stats.distinct_titles or 0

    # 5. Up-to-date Logic (Requires Title level check)
    # This is more complex to filter strictly by library if a title bridges libraries,
    # but we'll use the TitleDB coverage logic globally for now.
    all_titles_count = Titles.query.count() # Total in database
    titles_db_count = titles.get_titles_count()
    
    # Status breakdown (Global titles)
    # Note: We still use the library cache for genre and status for now if no filter
    # If filtered, we'll need to recalculate from DB or use a simplified logic
    lib_data = library.load_library_from_disk()
    if not lib_data:
        games = library.generate_library()
    else:
        games = lib_data.get('library', []) if isinstance(lib_data, dict) else lib_data

    # Filter games list if library_id provided (Heuristic)
    filtered_games = games
    if library_id:
        # A bit expensive, but accurate to the library
        lib_path = Libraries.query.get(library_id).path
        filtered_games = [g for g in games if any(lib_path in f for f in g.get('files', []))]

    # Recalculate based on filtered list
    # Total owned should be all games in our library list, 
    # as items only appear there if we own at least one component (Base, Update or DLC)
    total_owned = len(filtered_games)
    up_to_date = len([g for g in filtered_games if g.get('status_color') == 'green' and g.get('has_base')])
    # Genre Distribution (from filtered list)
    genre_dist = {}
    for g in filtered_games:
        cats = g.get('category', [])
        if not cats: cats = ['Unknown']
        for c in cats:
            genre_dist[c] = genre_dist.get(c, 0) + 1
            
    # Recognition Logic (Check if the TitleID exists in TitleDB and has a name)
    # Titles are considered unrecognized if their name starts with "Unknown" or if they are purely generic
    recognized_games = len([g for g in filtered_games if g.get('name') and not g.get('name', '').startswith('Unknown')])
    recognition_rate = round((recognized_games / total_owned * 100), 1) if total_owned > 0 else 0

    coverage_pct = round((total_owned / titles_db_count * 100), 2) if titles_db_count > 0 else 0
    keys_valid = app_settings.get('titles', {}).get('valid_keys', False)

    # TitleDB Info
    active_src = titledb.get_active_source_info()
    source_name = active_src.get('name', 'Nenhuma') if active_src else 'Nenhuma'

    return jsonify({
        'libraries': libraries_list,
        'library': {
            'total_titles': len(filtered_games),
            'total_owned': total_owned,
            'total_bases': total_owned_bases,
            'total_updates': total_owned_updates,
            'total_dlcs': total_owned_dlcs,
            'total_size': total_size,
            'total_size_formatted': format_size_py(total_size),
            'up_to_date': up_to_date,
            'pending': total_owned - up_to_date,
            'completion_rate': round((up_to_date / total_owned * 100), 1) if total_owned > 0 else 0
        },
        'titledb': {
            'total_available': titles_db_count,
            'coverage_pct': coverage_pct,
            'source_name': source_name
        },
        'identification': {
            'total_files': total_files,
            'identified_pct': id_rate,
            'recognition_pct': recognition_rate,
            'unidentified_count': unidentified_files,
            'unrecognized_count': total_owned - recognized_games,
            'keys_valid': keys_valid
        },
        'genres': genre_dist,
        'recent': filtered_games[:8]
    })

# --- New Feature APIs (Tags, Wishlist, Activity) ---

@main_bp.route('/api/tags', methods=['GET', 'POST'])
@access_required('shop')
def tags_api():
    if request.method == 'GET':
        tags = Tag.query.all()
        return jsonify([{'id': t.id, 'name': t.name, 'color': t.color, 'icon': t.icon} for t in tags])
    
    # POST - Create tag (Admin only)
    if not current_user.has_access('admin'):
        return jsonify({'error': 'Unauthorized'}), 403
        
    data = request.json
    if not data or 'name' not in data:
        return jsonify({'error': 'Name is required'}), 400
        
    tag = Tag(name=data['name'], color=data.get('color', '#3273dc'), icon=data.get('icon', 'bi-tag'))
    db.session.add(tag)
    try:
        db.session.commit()
        log_activity('tag_created', details={'name': tag.name}, user_id=current_user.id)
        return jsonify({'id': tag.id, 'name': tag.name})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@main_bp.route('/api/tags/<int:tag_id>', methods=['DELETE'])
@access_required('admin')
def delete_tag_api(tag_id):
    tag = db.session.get(Tag, tag_id)
    if tag:
        name = tag.name
        db.session.delete(tag)
        db.session.commit()
        log_activity('tag_deleted', details={'name': name}, user_id=current_user.id)
    return jsonify({'success': True})

@main_bp.route('/api/titles/<title_id>/tags', methods=['GET', 'POST', 'DELETE'])
@access_required('shop')
def title_tags_api(title_id):
    title_id = title_id.upper()
    if request.method == 'GET':
        tags = db.session.query(Tag).join(TitleTag).filter(TitleTag.title_id == title_id).all()
        return jsonify([{'id': t.id, 'name': t.name, 'color': t.color} for t in tags])
    
    if request.method == 'POST':
        tag_id = request.json.get('tag_id')
        if not tag_id: return jsonify({'error': 'tag_id required'}), 400
        # Check if exists
        exists = TitleTag.query.filter_by(title_id=title_id, tag_id=tag_id).first()
        if not exists:
            tt = TitleTag(title_id=title_id, tag_id=tag_id)
            db.session.add(tt)
            db.session.commit()
        return jsonify({'success': True})

    if request.method == 'DELETE':
        tag_id = request.json.get('tag_id')
        tt = TitleTag.query.filter_by(title_id=title_id, tag_id=tag_id).first()
        if tt:
            db.session.delete(tt)
            db.session.commit()
        return jsonify({'success': True})

@main_bp.route('/api/wishlist', methods=['GET', 'POST'])
@access_required('shop')
def wishlist_api():
    if request.method == 'GET':
        items = Wishlist.query.filter_by(user_id=current_user.id).all()
        return jsonify([{
            'id': i.id, 
            'title_id': i.title_id, 
            'added_date': i.added_date.isoformat(),
            'priority': i.priority,
            'notes': i.notes
        } for i in items])
    
    data = request.json
    if not data or 'title_id' not in data:
        return jsonify({'error': 'title_id required'}), 400
    
    # Check if already in wishlist
    exists = Wishlist.query.filter_by(user_id=current_user.id, title_id=data['title_id'].upper()).first()
    if exists:
        return jsonify({'error': 'Already in wishlist'}), 400
        
    item = Wishlist(
        user_id=current_user.id,
        title_id=data['title_id'].upper(),
        priority=data.get('priority', 0),
        notes=data.get('notes', '')
    )
    db.session.add(item)
    db.session.commit()
    log_activity('wishlist_added', title_id=item.title_id, user_id=current_user.id)
    return jsonify({'success': True})

@main_bp.route('/api/wishlist/<title_id>', methods=['PUT'])
@access_required('shop')
def update_wishlist_api(title_id):
    item = Wishlist.query.filter_by(user_id=current_user.id, title_id=title_id.upper()).first()
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    
    data = request.json
    if 'priority' in data:
        item.priority = int(data['priority'])
    if 'notes' in data:
        item.notes = data['notes']
        
    db.session.commit()
    return jsonify({'success': True})

@main_bp.route('/api/wishlist/<title_id>', methods=['DELETE'])
@access_required('shop')
def delete_wishlist_api(title_id):
    item = Wishlist.query.filter_by(user_id=current_user.id, title_id=title_id.upper()).first()
    if item:
        db.session.delete(item)
        db.session.commit()
        log_activity('wishlist_removed', title_id=title_id.upper(), user_id=current_user.id)
    return jsonify({'success': True})

@main_bp.route('/wishlist')
@login_required
def wishlist_page():
    return render_template('wishlist.html', title='Wishlist')

@main_bp.route('/api/wishlist/export', methods=['GET'])
@access_required('shop')
def export_wishlist_api():
    format_type = request.args.get('format', 'json').lower()
    items = Wishlist.query.filter_by(user_id=current_user.id).all()
    
    # Enrich data
    data = []
    for i in items:
        tInfo = titles.get_game_info(i.title_id)
        data.append({
            'title_id': i.title_id,
            'name': tInfo.get('name', 'Unknown'),
            'priority': i.priority,
            'added_date': i.added_date.isoformat(),
            'notes': i.notes or ''
        })

    if format_type == 'json':
        return jsonify(data)
    elif format_type == 'csv':
        import io
        import csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['TitleID', 'Name', 'Priority', 'Added Date', 'Notes'])
        for row in data:
            writer.writerow([row['title_id'], row['name'], row['priority'], row['added_date'], row['notes']])
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=myfoil_wishlist.csv"})
    elif format_type == 'html':
         # Simple HTML dump
        html = '<html><head><title>MyFoil Wishlist</title></head><body><h1>My Wishlist</h1><table border="1"><thead><tr><th>Name</th><th>ID</th><th>Priority</th></tr></thead><tbody>'
        for row in data:
            html += f'<tr><td>{row["name"]}</td><td>{row["title_id"]}</td><td>{row["priority"]}</td></tr>'
        html += '</tbody></table></body></html>'
        return Response(html, mimetype="text/html")
    
    return jsonify({'error': 'Unsupported format'}), 400

@main_bp.route('/api/activity', methods=['GET'])
@access_required('admin')
def activity_api():
    limit = request.args.get('limit', 50, type=int)
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(limit).all()
    
    import json
    results = []
    for l in logs:
        results.append({
            'timestamp': l.timestamp.isoformat(),
            'action': l.action_type,
            'title_id': l.title_id,
            'user': l.user_id, # Simplified
            'details': json.loads(l.details) if l.details else {}
        })
    return jsonify(results)

@main_bp.route('/api/plugins', methods=['GET'])
@access_required('admin')
def plugins_api():
    if not plugin_manager:
        return jsonify([])
    
    # Return all discovered plugins with their enabled status
    return jsonify(plugin_manager.discovered_plugins)

@main_bp.route('/api/plugins/toggle', methods=['POST'])
@access_required('admin')
def toggle_plugin_api():
    data = request.json
    plugin_id = data.get('id')
    enabled = data.get('enabled', True)
    
    if not plugin_id:
        return jsonify({'error': 'Plugin ID required'}), 400
        
    # 1. Update settings file
    import settings
    settings.toggle_plugin_settings(plugin_id, enabled)
    
    # 2. Reload plugins in the manager to reflect changes
    # Note: This won't "unload" already loaded classes from memory, but will 
    # stop them from being active if reload logic is implemented correctly.
    # For now, it updates the discovered_plugins list and future events will skip it.
    disabled_plugins = settings.load_settings(force=True).get('plugins', {}).get('disabled', [])
    plugin_manager.load_plugins(disabled_plugins)
    
    return jsonify({'success': True})

# Cloud API
@main_bp.route('/api/cloud/auth/<provider>', methods=['GET'])
@access_required('admin')
def cloud_auth_api(provider):
    if not cloud_manager:
        return jsonify({'error': 'Cloud manager not initialized'}), 500
    
    redirect_uri = url_for('main.cloud_callback_api', provider=provider, _external=True)
    auth_url = cloud_manager.get_auth_url(provider, redirect_uri)
    
    if not auth_url:
        return jsonify({'error': 'Provider not configured or disabled'}), 400
        
    return jsonify({'auth_url': auth_url})

@main_bp.route('/api/cloud/callback/<provider>', methods=['GET', 'POST'])
def cloud_callback_api(provider):
    # This endpoint receives the code from Google
    if request.method == 'GET':
        code = request.args.get('code')
        error = request.args.get('error')
        if error:
            return f"Error: {error}"
            
        if code:
            redirect_uri = url_for('main.cloud_callback_api', provider=provider, _external=True)
            if cloud_manager.authenticate(provider, code, redirect_uri):
                return "Authentication successful! You can close this window."
            else:
                return "Authentication failed.", 500
    
    # POST for manual code entry if needed
    data = request.json
    code = data.get('code')
    redirect_uri = data.get('redirect_uri')
    
    if cloud_manager.authenticate(provider, code, redirect_uri):
        return jsonify({'success': True})
    return jsonify({'success': False}), 400

@main_bp.route('/api/cloud/status', methods=['GET'])
@access_required('admin')
def cloud_status_api():
    if not cloud_manager:
        return jsonify({})
    
    results = {}
    for name, provider in cloud_manager.providers.items():
        results[name] = {
            'configured': True,
            'authenticated': (hasattr(provider, 'creds') and provider.creds is not None) or \
                             (hasattr(provider, 'access_token') and provider.access_token is not None)
        }
    return jsonify(results)

@main_bp.route('/api/cloud/files/<provider>', methods=['GET'])
@access_required('admin')
def cloud_files_api(provider):
    folder_id = request.args.get('folder_id')
    files = cloud_manager.list_files(provider, folder_id)
    return jsonify({'files': files})

# Create global app instance
app = create_app()

if __name__ == '__main__':
    logger.info(f'Build Version: {BUILD_VERSION}')
    logger.info('Starting server on port 8465...')
    socketio.run(app, debug=False, use_reloader=False, host="0.0.0.0", port=8465)
    # Shutdown server
    logger.info('Shutting down server...')
    watcher.stop()
    watcher_thread.join()
    logger.debug('Watcher thread terminated.')
    # Shutdown scheduler
    app.scheduler.shutdown()
    logger.debug('Scheduler terminated.')
