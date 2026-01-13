from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, Response
from flask_login import LoginManager
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
from sqlalchemy import event
from sqlalchemy.engine import Engine

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
        # Clear library cache to force regeneration with new TitleDB data
        if os.path.exists(LIBRARY_CACHE_FILE):
            os.remove(LIBRARY_CACHE_FILE)
            logger.info("Library cache cleared after TitleDB update.")
        logger.info("TitleDB update job completed.")
        return True
    except Exception as e:
        logger.error(f"Error during TitleDB update job: {e}")
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
                job_id=f'scan_library_rescheduled_{datetime.now().timestamp()}',
                func=scan_library_job,
                run_once=True,
                start_date=datetime.now().replace(microsecond=0) + timedelta(minutes=5)
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
        scan_library()
        post_library_change()
        logger.info("Library scan job completed.")
    except Exception as e:
        logger.error(f"Error during library scan job: {e}")
    finally:
        with scan_lock:
            scan_in_progress = False

def update_db_and_scan_job():
    logger.info("Running update job (TitleDB update and library scan)...")
    update_titledb_job()
    scan_library_job()
    logger.info("Update job completed.")

def init():
    global watcher
    global watcher_thread
    # Create and start the file watcher
    logger.info('Initializing File Watcher...')
    watcher = Watcher(on_library_change)
    watcher_thread = threading.Thread(target=watcher.run)
    watcher_thread.daemon = True
    watcher_thread.start()

    # Load initial configuration
    logger.info('Loading initial configuration...')
    reload_conf()

    # init libraries
    library_paths = app_settings['library']['paths']
    init_libraries(app, watcher, library_paths)

     # Initialize job scheduler
    logger.info('Initializing Scheduler...')
    init_scheduler(app)
    
    # Schedule periodic tasks (run every 24h, starting now)
    app.scheduler.add_job(
        job_id='update_db_and_scan',
        func=update_db_and_scan_job,
        interval=timedelta(hours=24),
        run_first=True
    )

os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

## Global variables
app_settings = {}
# Create a global variable and lock for scan_in_progress
scan_in_progress = False
scan_lock = threading.Lock()
# Global flag for titledb update status
is_titledb_update_running = False
titledb_update_lock = threading.Lock()

# Configure logging
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

# Create main logger
logger = logging.getLogger('main')
logger.setLevel(logging.DEBUG)

# Apply filter to hide date from http access logs
logging.getLogger('werkzeug').addFilter(FilterRemoveDateFromWerkzeugLogs())

# Suppress specific Alembic INFO logs
logging.getLogger('alembic.runtime.migration').setLevel(logging.WARNING)

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

    post_library_change()

def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = MYFOIL_DB
    app.config['SECRET_KEY'] = get_or_create_secret_key()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    app.register_blueprint(auth_blueprint)



    # Initialize I18n
    app.i18n = I18n(app)

    return app

# Create app
app = create_app()

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
    strategy="fixed-window"
)

@app.context_processor
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
                auth_success, auth_error, _ = basic_auth(request)
            if not auth_success:
                return tinfoil_error(auth_error)
        # Auth success
        return f(*args, **kwargs)
    return _tinfoil_access

def access_shop():
    total_files = Files.query.count()
    
    # Owned counts
    total_games = Apps.query.filter_by(app_type=APP_TYPE_BASE, owned=True).count()
    total_dlcs = Apps.query.filter_by(app_type=APP_TYPE_DLC, owned=True).count()
    total_updates = Apps.query.filter_by(app_type=APP_TYPE_UPD, owned=True).count()
    
    # Explicitly calculate missing counts
    # Missing Games: Total in DB - Owned
    # Note: Titles table has all known titles (if imported from TitleDB)
    # But usually Titles table only populates if files are found or titles are known?
    # Actually library.py logic: Titles are added if found in file identification or if missing apps are added.
    # missing_games = Apps.query.filter_by(app_type=APP_TYPE_BASE, owned=False).count()
    
    # Let's trust the Apps table "owned=False" entries which are populated by 'add_missing_apps_to_db'
    missing_games = Apps.query.filter_by(app_type=APP_TYPE_BASE, owned=False).count()
    missing_updates = Apps.query.filter_by(app_type=APP_TYPE_UPD, owned=False).count()
    missing_dlcs = Apps.query.filter_by(app_type=APP_TYPE_DLC, owned=False).count()
    
    # For "missing update games", we normally mean games that have an update available but we don't have the latest.
    # This is slightly different from "missing_updates" which counts total missing update files.
    # "Games with missing updates" = Titles where up_to_date=False
    games_missing_updates = Titles.query.filter_by(up_to_date=False, have_base=True).count()
    
    # "Games with missing DLCs" = Titles where complete=False
    games_missing_dlcs = Titles.query.filter_by(complete=False, have_base=True).count()

    return render_template('index.html', title='Library', 
                           admin_account_created=admin_account_created(), 
                           valid_keys=app_settings['titles']['valid_keys'],
                           total_files=total_files,
                           total_games=total_games,
                           total_dlcs=total_dlcs,
                           total_updates=total_updates,
                           missing_games=missing_games,
                           missing_updates=missing_updates,
                           missing_dlcs=missing_dlcs,
                           games_missing_updates=games_missing_updates,
                           games_missing_dlcs=games_missing_dlcs,
                           games=None)

@access_required('shop')
def access_shop_auth():
    return access_shop()

@app.route('/')
def index():

    @tinfoil_access
    def access_tinfoil_shop():
        shop = {
            "success": app_settings['shop']['motd']
        }
        
        if request.verified_host is not None:
            # enforce client side host verification
            shop["referrer"] = f"https://{request.verified_host}"
            
        shop["files"] = gen_shop_files(db)

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

@app.route('/settings')
@access_required('admin')
def settings_page():
    with open(os.path.join(TITLEDB_DIR, 'languages.json')) as f:
        languages = json.load(f)
        languages = dict(sorted(languages.items()))
    return render_template(
        'settings.html',
        title='Settings',
        languages_from_titledb=languages,
        admin_account_created=admin_account_created(),
        valid_keys=app_settings['titles']['valid_keys'],
        active_source=titledb.get_active_source_info())

@app.get('/api/settings')
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

@app.post('/api/settings/titles')
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

@app.route('/api/settings/regions')
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

@app.route('/api/settings/languages')
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

@app.post('/api/settings/shop')
def set_shop_settings_api():
    data = request.json
    set_shop_settings(data)
    reload_conf()
    resp = {
        'success': True,
        'errors': []
    } 
    return jsonify(resp)

@app.route('/api/settings/library/paths', methods=['GET', 'POST', 'DELETE'])
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
        resp = {
            'success': True,
            'errors': [],
            'paths': app_settings['library']['paths']
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

@app.post('/api/settings/keys')
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


@app.route('/api/settings/titledb/sources', methods=['GET', 'POST', 'PUT', 'DELETE'])
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




@app.post('/api/settings/titledb/sources/reorder')
@access_required('admin')
def reorder_titledb_sources_api():
    """
    Expects JSON: { "source_name_1": 0, "source_name_2": 1, ... }
    """
    data = request.json
    if not data:
        return jsonify({'success': False, 'errors': ['No data provided']})
    
    success = titledb.update_titledb_priorities(data)
    return jsonify({
        'success': success
    })

@app.post('/api/settings/titledb/update')
@access_required('admin')
def force_titledb_update_api():
    """Force a TitleDB update in background"""
    threading.Thread(target=update_titledb_job, args=(True,)).start()
    return jsonify({
        'success': True,
        'message': 'Update started in background'
    })


@app.route('/api/titles', methods=['GET'])
@access_required('shop')
def get_all_titles_api():
    titles_library = generate_library()

    return jsonify({
        'total': len(titles_library),
        'games': titles_library
    })

@app.route('/api/set_language/<lang>', methods=['POST'])
def set_language(lang):
    if lang in ['en', 'pt_BR']:
        resp = jsonify({'success': True})
        # Set cookie for 1 year
        resp.set_cookie('language', lang, max_age=31536000)
        return resp
    return jsonify({'success': False, 'error': 'Invalid language'}), 400

@app.route('/api/get_game/<int:id>')
@tinfoil_access
def serve_game(id):
    # TODO add download count increment
    file = Files.query.get(id)
    if not file:
        return "File not found", 404
    filedir, filename = os.path.split(file.filepath)
    return send_from_directory(filedir, filename)

@app.route('/api/app_info/<id>')
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

    if not title_obj:
        # Maybe it's a DLC app_id, try to find base TitleID
        titles_lib.load_titledb() # Ensure loaded
        base_tid, _ = titles_lib.identify_appId(tid)
        if base_tid:
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
        # Game/Title not in our database at all
        result = info.copy()
        result['id'] = tid
        result['app_id'] = tid
        result['owned_version'] = 0
        result['has_base'] = False
        result['has_latest_version'] = False
        result['has_all_dlcs'] = False
        result['owned'] = False
        result['files'] = []
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
                'size_formatted': format_size_py(f.size)
            })
    
    # Deduplicate files by ID
    seen_ids = set()
    unique_base_files = []
    for f in base_files:
        if f['id'] not in seen_ids:
            unique_base_files.append(f)
            seen_ids.add(f['id'])

    # Updates and DLCs (for detailed listing)
    available_versions = titles_lib.get_all_existing_versions(tid)
    version_release_dates = {v['version']: v['release_date'] for v in available_versions}
    
    update_apps = [a for a in all_title_apps if a['app_type'] == APP_TYPE_UPD]
    updates_list = []
    for upd in update_apps:
        v_int = int(upd['app_version'])
        updates_list.append({
            'version': v_int,
            'owned': upd['owned'],
            'release_date': version_release_dates.get(v_int, 'Unknown')
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
        owned = any(a['owned'] for a in dlc_apps_grouped.get(dlc_id, []))
        dlcs_list.append({
            'app_id': dlc_id,
            'name': titles_lib.get_game_info(dlc_id).get('name', f'DLC {dlc_id}'),
            'owned': owned
        })

    result = info.copy()
    result['id'] = tid
    result['app_id'] = tid
    result['title_id'] = tid
    result['has_base'] = title_obj.have_base
    result['has_latest_version'] = title_obj.up_to_date
    result['has_all_dlcs'] = title_obj.complete
    result['files'] = unique_base_files
    result['updates'] = sorted(updates_list, key=lambda x: x['version'])
    result['dlcs'] = sorted(dlcs_list, key=lambda x: x['name'])
    result['owned_version'] = max([u['version'] for u in updates_list if u['owned']], default=0)
    result['category'] = info.get('category', []) # Genre/Categories
    
    return jsonify(result)

@app.route('/api/files/unidentified')
@access_required('admin')
def get_unidentified_files_api():
    files = get_all_unidentified_files()
    return jsonify([{
        'id': f.id,
        'filename': f.filename,
        'filepath': f.filepath,
        'size': f.size,
        'size_formatted': format_size_py(f.size),
        'error': f.identification_error
    } for f in files])

@app.route('/api/files/delete/<int:file_id>', methods=['POST'])
@access_required('admin')
def delete_file_api(file_id):
    success, error = delete_file_from_db_and_disk(file_id)
    return jsonify({'success': success, 'error': error})

def format_size_py(size):
    if size is None: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


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

@app.post('/api/library/scan')
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
        if path is None:
            scan_library()
        else:
            scan_library_path(path)
    except Exception as e:
        errors.append(e)
        success = False
        logger.error(f"Error during library scan: {e}")
    finally:
        with scan_lock:
            scan_in_progress = False

    post_library_change()
    resp = {
        'success': success,
        'errors': errors
    } 
    return jsonify(resp)

def scan_library():
    logger.info(f'Scanning whole library ...')
    libraries = get_libraries()
    for library in libraries:
        scan_library_path(library.path) # Only scan, identification will be done globally

@app.route('/api/library')
@access_required('shop')
def library_api():
    # Fast check for cache and ETag
    cached = load_library_from_disk()
    if cached and 'hash' in cached:
        etag = cached['hash']
        if request.headers.get('If-None-Match') == etag:
            return '', 304
    
    # generate_library will use cache if force=False (default)
    lib_data = generate_library()
    
    # We need the hash for the header, so we reload from disk to get the full dict
    # or we can modify generate_library to return it. 
    # For now, just reload the small file header.
    full_cache = load_library_from_disk()
    resp = jsonify(lib_data)
    if full_cache and 'hash' in full_cache:
        resp.set_etag(full_cache['hash'])
    return resp

@app.route('/api/status')
def process_status_api():
    return jsonify({
        'scanning': scan_in_progress,
        'updating_titledb': is_titledb_update_running
    })

if __name__ == '__main__':
    logger.info(f'Build Version: {BUILD_VERSION}')
    logger.info('Starting initialization of MyFoil...')
    init_db(app)
    init_users(app)
    init()
    logger.info('Registered routes:')
    for rule in app.url_map.iter_rules():
        logger.info(f"{rule.endpoint}: {rule}")
    logger.info('Initialization steps done, starting server...')
    app.run(debug=False, use_reloader=False, host="0.0.0.0", port=8465)
    # Shutdown server
    logger.info('Shutting down server...')
    watcher.stop()
    watcher_thread.join()
    logger.debug('Watcher thread terminated.')
    # Shutdown scheduler
    app.scheduler.shutdown()
    logger.debug('Scheduler terminated.')
