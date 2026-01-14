import hashlib
from constants import *
from db import *
from metrics import FILES_IDENTIFIED, IDENTIFICATION_DURATION, LIBRARY_SIZE
import titles as titles_lib
import datetime
from pathlib import Path
from utils import *
import threading

# Session-level cache
_LIBRARY_CACHE = None
_CACHE_LOCK = threading.Lock()

ALLOWED_EXTENSIONS = {'.nsp', '.nsz', '.xci', '.xcz'}
MAX_FILE_SIZE = 50 * 1024 * 1024 * 1024  # 50GB

def validate_file(filepath):
    """
    Validate file before processing.
    Checks extension, size, symlinks, and basic header for Switch files.
    """
    path = Path(filepath)
    
    # 1. Check extension
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Extensão não permitida: {path.suffix}")
    
    # 2. Check existence and size
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")
        
    size = path.stat().st_size
    if size == 0:
        raise ValueError("Arquivo vazio")
    if size > MAX_FILE_SIZE:
        raise ValueError(f"Arquivo excede limite de tamanho (50GB)")
    
    # 3. Check for malicious symlinks
    if path.is_symlink():
        # Ensure it resolves within a allowed path (optional but safer)
        # We'll just log a warning for now as libraries can be spread out
        logger.warning(f"Processando symlink: {filepath}")

    # 4. Basic Header validation (Switch specific)
    try:
        with open(filepath, 'rb') as f:
            header = f.read(4)
            # NSP/NSZ starts with PFS0
            if path.suffix.lower() in ['.nsp', '.nsz']:
                if header != b'PFS0':
                    raise ValueError(f"Cabeçalho NSP inválido: {header}")
            # XCI/XCZ starts with HEAD at offset 0x100
            elif path.suffix.lower() in ['.xci', '.xcz']:
                f.seek(0x100)
                header_xci = f.read(4)
                if header_xci != b'HEAD':
                    raise ValueError(f"Cabeçalho XCI inválido: {header_xci}")
    except Exception as e:
        if isinstance(e, ValueError): raise
        raise ValueError(f"Erro ao ler cabeçalho do arquivo: {str(e)}")
    
    return True

def cleanup_metadata_files(path):
    """Recursively delete macOS metadata files (starting with ._)"""
    logger.info(f"Cleaning up macOS metadata files in {path}...")
    deleted_count = 0
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.startswith('._'):
                try:
                    os.remove(os.path.join(root, file))
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete metadata file {file}: {e}")
    if deleted_count > 0:
        logger.info(f"Deleted {deleted_count} metadata files.")

def add_library_complete(app, watcher, path):
    """Add a library to settings, database, and watchdog"""
    from settings import add_library_path_to_settings
    
    with app.app_context():
        # Add to settings
        success, errors = add_library_path_to_settings(path)
        if not success:
            return success, errors
        
        # Add to database
        add_library(path)
        
        # Add to watchdog
        watcher.add_directory(path)
        
        logger.info(f"Successfully added library: {path}")
        return True, []

def remove_library_complete(app, watcher, path):
    """Remove a library from settings, database, and watchdog with proper cleanup"""
    from settings import delete_library_path_from_settings
    
    with app.app_context():
        # Remove from watchdog first
        watcher.remove_directory(path)
        
        # Get library object before deletion
        library = Libraries.query.filter_by(path=path).first()
        if library:
            # Get all file IDs from this library before deletion
            file_ids = [f.id for f in library.files]
            
            # Update Apps table to remove file references and update ownership
            total_apps_updated = 0
            for file_id in file_ids:
                apps_updated = remove_file_from_apps(file_id)
                total_apps_updated += apps_updated
            
            # Remove titles that no longer have any owned apps
            titles_removed = remove_titles_without_owned_apps()
            
            # Delete library (cascade will delete files automatically)
            db.session.delete(library)
            db.session.commit()
            
            if titles_removed > 0:
                logger.info(f"Removed {titles_removed} titles with no owned apps.")
        
            log_activity('library_removed', details={'path': path})
        
        # Remove from settings
        success, errors = delete_library_path_from_settings(path)
        
        invalidate_library_cache()
        return success, errors

def init_libraries(app, watcher, paths):
    with app.app_context():
        # delete non existing libraries
        for library in get_libraries():
            path = library.path
            if not os.path.exists(path):
                logger.warning(f"Library {path} no longer exists, deleting from database.")
                # Use the complete removal function for consistency
                remove_library_complete(app, watcher, path)

        # add libraries and start watchdog
        for path in paths:
            # Check if library already exists in database
            existing_library = Libraries.query.filter_by(path=path).first()
            if not existing_library:
                # add library paths to watchdog if necessary
                watcher.add_directory(path)
                add_library(path)
            else:
                # Ensure watchdog is monitoring existing library
                watcher.add_directory(path)

def add_files_to_library(library, files):
    nb_to_identify = len(files)
    if isinstance(library, int) or library.isdigit():
        library_id = library
        library_path = get_library_path(library_id)
    else:
        library_path = library
        library_id = get_library_id(library_path)

    library_path = get_library_path(library_id)
    for n, filepath in enumerate(files):
        file = filepath.replace(library_path, "")
        logger.info(f'Getting file info ({n+1}/{nb_to_identify}): {file}')

        try:
            # Validate file before adding to DB
            validate_file(filepath)
            
            file_info = titles_lib.get_file_info(filepath)

            if file_info is None:
                logger.error(f'Failed to get info for file: {file} - file will be skipped.')
                continue

            new_file = Files(
                filepath = filepath,
                library_id = library_id,
                folder = file_info["filedir"],
                filename = file_info["filename"],
                extension = file_info["extension"],
                size = file_info["size"],
            )
            db.session.add(new_file)
            log_activity('file_added', title_id=file_info.get("titleId"), details={'filename': file_info["filename"], 'size': file_info["size"]})
        except Exception as e:
            logger.error(f"Validation failed for {file}: {str(e)}")
            continue

        # Commit every 100 files to avoid excessive memory use
        if (n + 1) % 100 == 0:
            db.session.commit()

    # Final commit
    db.session.commit()

def scan_library_path(library_path):
    cleanup_metadata_files(library_path)
    library_id = get_library_id(library_path)
    logger.info(f'Scanning library path {library_path} ...')
    if not os.path.isdir(library_path):
        logger.warning(f'Library path {library_path} does not exists.')
        return
    _, files = titles_lib.getDirsAndFiles(library_path)

    filepaths_in_library = get_library_file_paths(library_id)
    new_files = [f for f in files if f not in filepaths_in_library]
    add_files_to_library(library_id, new_files)
    set_library_scan_time(library_id)

def get_files_to_identify(library_id):
    non_identified_files = get_all_non_identified_files_from_library(library_id)
    if titles_lib.Keys.keys_loaded:
        files_to_identify_with_cnmt = get_files_with_identification_from_library(library_id, 'filename')
        non_identified_files = list(set(non_identified_files).union(files_to_identify_with_cnmt))
    return non_identified_files

def identify_library_files(library):
    if isinstance(library, int) or library.isdigit():
        library_id = library
        library_path = get_library_path(library_id)
    else:
        library_path = library
        library_id = get_library_id(library_path)
    files_to_identify = get_files_to_identify(library_id)
    nb_to_identify = len(files_to_identify)
    for n, file in enumerate(files_to_identify):
        try:
            file_id = file.id
            filepath = file.filepath
            filename = file.filename

            if not os.path.exists(filepath):
                logger.warning(f'Identifying file ({n+1}/{nb_to_identify}): {filename} no longer exists, clearing from database.')
                # Use helper to ensure ownership is updated
                remove_file_from_apps(file_id)
                Files.query.filter_by(id=file_id).delete(synchronize_session=False)
                db.session.commit()
                continue

            logger.info(f'Identifying file ({n+1}/{nb_to_identify}): {filename}')
            with IDENTIFICATION_DURATION.time():
                identification, success, file_contents, error = titles_lib.identify_file(filepath)
            
            if success and file_contents and not error:
                # Increment metrics
                FILES_IDENTIFIED.labels(app_type="multiple" if len(file_contents) > 1 else file_contents[0]["type"]).inc()
                # find all unique Titles ID to add to the Titles db
                title_ids = list(dict.fromkeys([c['title_id'] for c in file_contents]))

                for title_id in title_ids:
                    add_title_id_in_db(title_id)

                nb_content = 0
                for file_content in file_contents:
                    logger.info(f'Identifying file ({n+1}/{nb_to_identify}) - Found content Title ID: {file_content["title_id"]} App ID : {file_content["app_id"]} Title Type: {file_content["type"]} Version: {file_content["version"]}')
                    # now add the content to Apps
                    title_id_in_db = get_title_id_db_id(file_content["title_id"])
                    
                    # Check if app already exists
                    existing_app = get_app_by_id_and_version(
                        file_content["app_id"],
                        file_content["version"]
                    )
                    
                    if existing_app:
                        # Add file to existing app using many-to-many relationship
                        add_file_to_app(file_content["app_id"], file_content["version"], file_id)
                    else:
                        # Create new app entry and add file using many-to-many relationship
                        new_app = Apps(
                            app_id=file_content["app_id"],
                            app_version=file_content["version"],
                            app_type=file_content["type"],
                            owned=True,
                            title_id=title_id_in_db
                        )
                        db.session.add(new_app)
                        db.session.flush()  # Flush to get the app ID
                        
                        # Add the file to the new app
                        file_obj = get_file_from_db(file_id)
                        if file_obj:
                            new_app.files.append(file_obj)
                    
                    nb_content += 1

                if nb_content > 1:
                    file.multicontent = True
                file.nb_content = nb_content
                file.identified = True
            else:
                logger.warning(f"Error identifying file {filename}: {error}")
                file.identification_error = error
                file.identified = False

            file.identification_type = identification

        except Exception as e:
            logger.warning(f"Error identifying file {filename}: {e}")
            file.identification_error = str(e)
            file.identified = False

        # and finally update the File with identification info
        file.identification_attempts += 1
        file.last_attempt = datetime.datetime.now()

        # Commit every 100 files to avoid excessive memory use
        if (n + 1) % 100 == 0:
            db.session.commit()

    # Final commit
    db.session.commit()

def add_missing_apps_to_db():
    logger.info('Adding missing apps to database...')
    titles = get_all_titles()
    apps_added = 0
    
    for n, title in enumerate(titles):
        title_id = title.title_id
        title_db_id = get_title_id_db_id(title_id)
        
        # Add base game if not present
        existing_base = get_app_by_id_and_version(title_id, "0")
        
        if not existing_base:
            new_base_app = Apps(
                app_id=title_id,
                app_version="0",
                app_type=APP_TYPE_BASE,
                owned=False,
                title_id=title_db_id
            )
            db.session.add(new_base_app)
            apps_added += 1
            logger.debug(f'Added missing base app: {title_id}')
        
        # Add missing update versions
        title_versions = titles_lib.get_all_existing_versions(title_id)
        for version_info in title_versions:
            v_int = version_info['version']
            if v_int == 0: continue # Skip v0 for updates table
            
            version = str(v_int)
            update_app_id = title_id[:-3] + '800'  # Convert base ID to update ID
            
            existing_update = get_app_by_id_and_version(update_app_id, version)
            
            if not existing_update:
                new_update_app = Apps(
                    app_id=update_app_id,
                    app_version=version,
                    app_type=APP_TYPE_UPD,
                    owned=False,
                    title_id=title_db_id
                )
                db.session.add(new_update_app)
                apps_added += 1
                logger.debug(f'Added missing update app: {update_app_id} v{version}')
        
        # Add missing DLC
        title_dlc_ids = titles_lib.get_all_existing_dlc(title_id)
        for dlc_app_id in title_dlc_ids:
            dlc_versions = titles_lib.get_all_app_existing_versions(dlc_app_id)
            if dlc_versions:
                for dlc_version in dlc_versions:
                    existing_dlc = get_app_by_id_and_version(dlc_app_id, str(dlc_version))
                    
                    if not existing_dlc:
                        new_dlc_app = Apps(
                            app_id=dlc_app_id,
                            app_version=str(dlc_version),
                            app_type=APP_TYPE_DLC,
                            owned=False,
                            title_id=title_db_id
                        )
                        db.session.add(new_dlc_app)
                        apps_added += 1
                        logger.debug(f'Added missing DLC app: {dlc_app_id} v{dlc_version}')
        
        # Commit every 100 titles to avoid excessive memory use
        if (n + 1) % 100 == 0:
            db.session.commit()
            logger.info(f'Processed {n + 1}/{len(titles)} titles, added {apps_added} missing apps so far')
    
    # Final commit
    db.session.commit()
    logger.info(f'Finished adding missing apps to database. Total apps added: {apps_added}')

def process_library_identification(app):
    logger.info(f"Starting library identification process for all libraries...")
    try:
        with app.app_context():
            libraries = get_libraries()
            for library in libraries:
                identify_library_files(library.path)

    except Exception as e:
        logger.error(f"Error during library identification process: {e}")
    logger.info(f"Library identification process for all libraries completed.")

def update_titles():
    # Remove titles that no longer have any owned apps
    titles_removed = remove_titles_without_owned_apps()
    if titles_removed > 0:
            logger.info(f"Removed {titles_removed} titles with no owned apps.")

    # Optimized query to fetch titles and their apps in fixed number of queries
    titles = Titles.query.options(joinedload(Titles.apps)).all()
    for n, title in enumerate(titles):
        have_base = False
        up_to_date = False
        complete = False

        title_id = title.title_id
        # Use child apps collection instead of a new query
        title_apps = [to_dict(app) for app in title.apps]

        # check have_base - look for owned base apps
        owned_base_apps = [app for app in title_apps if app.get('app_type') == APP_TYPE_BASE and app.get('owned')]
        have_base = len(owned_base_apps) > 0

        # Maximum owned version (including base and update)
        owned_versions = [int(a['app_version']) for a in title_apps if a.get('owned')]
        max_owned_version = max(owned_versions) if owned_versions else -1

        # Available updates from titledb via versions.json
        available_versions = titles_lib.get_all_existing_versions(title_id)
        max_available_version = max([v['version'] for v in available_versions], default=0)

        # check up_to_date - consider current max owned vs max available
        up_to_date = max_owned_version >= max_available_version

        # check complete - latest version of all available DLC are owned
        available_dlc_apps = [app for app in title_apps if app.get('app_type') == APP_TYPE_DLC]
        
        if not available_dlc_apps:
            # No DLC available, consider complete
            complete = True
        else:
            # Group DLC by app_id and find latest version for each
            dlc_by_id = {}
            for app in available_dlc_apps:
                app_id = app['app_id']
                version = int(app['app_version'])
                if app_id not in dlc_by_id or version > dlc_by_id[app_id]['version']:
                    dlc_by_id[app_id] = {
                        'version': version,
                        'owned': app.get('owned', False)
                    }
            
            # Check if latest version of each DLC is owned
            complete = all(dlc_info['owned'] for dlc_info in dlc_by_id.values())

        title.have_base = have_base
        title.up_to_date = up_to_date
        title.complete = complete

        # Commit every 100 titles to avoid excessive memory use
        if (n + 1) % 100 == 0:
            db.session.commit()

    db.session.commit()

def get_library_status(title_id):
    title = get_title(title_id)
    title_apps = get_all_title_apps(title_id)

    available_versions = titles_lib.get_all_existing_versions(title_id)
    for version in available_versions:
        if len(list(filter(lambda x: x.get('app_type') == APP_TYPE_UPD and str(x.get('app_version')) == str(version['version']), title_apps))):
            version['owned'] = True
        else:
            version['owned'] = False

    library_status = {
        'has_base': title.have_base,
        'has_latest_version': title.up_to_date,
        'version': available_versions,
        'has_all_dlcs': title.complete
    }
    return library_status

def compute_apps_hash():
    """
    Computes a hash of all Apps table content to detect changes in library state.
    """
    hash_md5 = hashlib.md5()
    apps = get_all_apps()
    
    # Sort apps with safe handling of None values
    for app in sorted(apps, key=lambda x: (x['app_id'] or '', x['app_version'] or '')):
        hash_md5.update((app['app_id'] or '').encode())
        hash_md5.update((app['app_version'] or '').encode())
        hash_md5.update((app['app_type'] or '').encode())
        hash_md5.update(str(app['owned'] or False).encode())
        hash_md5.update((app['title_id'] or '').encode())
        # Include file metadata in hash to detect additions/deletions
        if 'files_info' in app:
            for f in sorted(app['files_info'], key=lambda x: x['path']):
                hash_md5.update(f['path'].encode())
                hash_md5.update(str(f.get('size', 0)).encode())
        
    # Include tags in hash (from Titles)
    titles_with_tags = db.session.query(Titles.title_id, Tag.name).join(Titles.tags).all()
    for tid, tname in sorted(titles_with_tags):
        hash_md5.update(tid.encode())
        hash_md5.update(tname.encode())
        
    return hash_md5.hexdigest()

def is_library_unchanged():
    cache_path = Path(LIBRARY_CACHE_FILE)
    if not cache_path.exists():
        return False

    saved_library = load_library_from_disk()
    if not saved_library:
        return False

    if not saved_library.get('hash'):
        return False

    current_hash = compute_apps_hash()
    return saved_library['hash'] == current_hash

def save_library_to_disk(library_data):
    cache_path = Path(LIBRARY_CACHE_FILE)
    # Ensure cache directory exists
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_json(cache_path, library_data)

def load_library_from_disk():
    cache_path = Path(LIBRARY_CACHE_FILE)
    if not cache_path.exists():
        return None

    try:
        with cache_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def invalidate_library_cache():
    global _LIBRARY_CACHE
    with _CACHE_LOCK:
        _LIBRARY_CACHE = None

def get_game_info_item(tid, title_data):
    """Generate a single game item for the library list"""
    # All apps for this title (already pre-loaded in title_data['apps'])
    all_title_apps = title_data['apps']
    
    # We only show games that have at least one OWNED app in the library
    owned_apps = [a for a in all_title_apps if a.get('owned')]
    if not owned_apps:
        return None
        
    # Base info from TitleDB
    info = titles_lib.get_game_info(tid)
    if not info:
        info = {'name': f'Unknown ({tid})', 'iconUrl': '', 'publisher': 'Unknown'}
        
    game = info.copy()
    game['title_id'] = tid
    game['id'] = tid  # For display on card as game ID
    
    # Owned version considers Base and Updates
    owned_versions = [int(a['app_version']) for a in all_title_apps if a.get('owned')]
    game['owned_version'] = max(owned_versions) if owned_versions else 0
    game['display_version'] = str(game['owned_version'])

    def normalize_date(d):
        if not d: return ""
        d = str(d).strip()
        # Handle YYYYMMDD
        if len(d) == 8 and d.isdigit():
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        return d

    # Available versions from versions.json
    available_versions = titles_lib.get_all_existing_versions(tid)
    latest_v = max(available_versions, key=lambda x: x['version'], default=None)
    game['latest_version_available'] = latest_v['version'] if latest_v else 0
    game['latest_release_date'] = normalize_date(latest_v['release_date']) if latest_v else ''
    
    # Ensure release_date is consistently available for sorting
    original_release = normalize_date(game.get('release_date'))
    game['release_date'] = original_release or game['latest_release_date'] or ''

    # Status indicators
    game['has_base'] = any(a['app_type'] == APP_TYPE_BASE and a['owned'] for a in all_title_apps)
    game['has_latest_version'] = game['owned_version'] >= game['latest_version_available']
    
    all_possible_dlc_ids = titles_lib.get_all_existing_dlc(tid)
    owned_dlc_ids = list(set([a['app_id'] for a in all_title_apps if a['app_type'] == APP_TYPE_DLC and a['owned']]))
    game['has_all_dlcs'] = all(d in owned_dlc_ids for d in all_possible_dlc_ids) if all_possible_dlc_ids else True

    # Check for redundant updates (more than 1 update file)
    owned_updates = [a for a in all_title_apps if a['app_type'] == APP_TYPE_UPD and a['owned']]
    game['updates_count'] = len(owned_updates)
    game['has_redundant_updates'] = game['updates_count'] > 1

    game['owned'] = len(owned_apps) > 0
    
    # Determine status color for UI and numeric score for sorting
    # Score: 2 = Complete (Green), 1 = Pending (Orange), 0 = No Base (Red/Orange)
    if not game['has_base']:
        game['status_color'] = 'orange'
        game['status_score'] = 0
    elif not game['has_latest_version'] or not game['has_all_dlcs']:
        game['status_color'] = 'orange'
        game['status_score'] = 1
    else:
        game['status_color'] = 'green'
        game['status_score'] = 2

    # Added date proxy (minimum file ID)
    file_ids = []
    for a in all_title_apps:
        if a.get('owned') and 'files_info' in a:
            file_ids.extend([f.get('id') for f in a['files_info'] if f.get('id')])
    game['added_at'] = min(file_ids) if file_ids else 999999



    # Tags from Title object
    game['tags'] = title_data.get('tags', [])
    
    # Files and details
    game['base_files'] = []
    base_app_entries = [a for a in all_title_apps if a['app_type'] == APP_TYPE_BASE and a['owned']]
    for b in base_app_entries:
        if 'files_info' in b:
            game['base_files'].extend([f['path'] for f in b['files_info']])
    
    game['base_files'] = list(set(game['base_files']))

    # Calculate total size of owned files
    total_size = 0
    for a in all_title_apps:
        if a.get('owned') and 'files_info' in a:
            for f in a['files_info']:
                total_size += f.get('size', 0)
    
    game['size'] = total_size
    game['size_formatted'] = format_size_py(total_size)
    update_apps = [a for a in all_title_apps if a['app_type'] == APP_TYPE_UPD]
    version_release_dates = {v['version']: v['release_date'] for v in available_versions}
    
    version_list = []
    for upd in update_apps:
        v_int = int(upd['app_version'])
        if v_int == 0: continue # Skip base version in updates list
        version_list.append({
            'version': v_int,
            'owned': upd['owned'],
            'release_date': version_release_dates.get(v_int, 'Unknown'),
            'files': upd.get('files', []) if upd['owned'] else []
        })
    
    game['updates'] = sorted(version_list, key=lambda x: x['version'])
    

    # DLC details
    dlcs_by_id = {}
    for dlc_id in all_possible_dlc_ids:
        dlcs_by_id[dlc_id] = {
            'app_id': dlc_id,
            'name': titles_lib.get_game_info(dlc_id).get('name', f'DLC {dlc_id}'),
            'owned': False,
            'latest_version': 0,
            'owned_version': 0
        }
        
    dlc_apps = [a for a in all_title_apps if a['app_type'] == APP_TYPE_DLC]
    for dlc_app in dlc_apps:
        aid = dlc_app['app_id']
        v = int(dlc_app['app_version'])
        if aid not in dlcs_by_id:
            dlcs_by_id[aid] = {
                'app_id': aid,
                'name': titles_lib.get_game_info(aid).get('name', f'DLC {aid}'),
                'owned': False,
                'latest_version': 0,
                'owned_version': 0
            }
        if dlc_app['owned']:
            dlcs_by_id[aid]['owned'] = True
            dlcs_by_id[aid]['owned_version'] = max(dlcs_by_id[aid]['owned_version'], v)
        dlcs_by_id[aid]['latest_version'] = max(dlcs_by_id[aid]['latest_version'], v)

    game['dlcs'] = sorted(dlcs_by_id.values(), key=lambda x: x['name'])
    return game

def generate_library(force=False):
    """Generate the game library grouped by TitleID, using cached version if unchanged"""
    global _LIBRARY_CACHE
    
    if not force:
        with _CACHE_LOCK:
            if _LIBRARY_CACHE:
                return _LIBRARY_CACHE
            
            # Try loading from disk
            saved_library = load_library_from_disk()
            if saved_library and 'library' in saved_library:
                _LIBRARY_CACHE = saved_library['library']
                return _LIBRARY_CACHE

    logger.info(f'Generating library (force={force})...')
    titles_lib.load_titledb()
    
    # Get all Titles known to the system with their apps and files pre-loaded
    all_titles_data = get_all_titles_with_apps()
    games_info = []

    for title_data in all_titles_data:
        game = get_game_info_item(title_data['title_id'], title_data)
        if game:
            games_info.append(game)
    
    sorted_library = sorted(games_info, key=lambda x: x.get("name", "Unrecognized") or "Unrecognized")
    
    library_data = {
        'hash': compute_apps_hash(),
        'library': sorted_library
    }

    save_library_to_disk(library_data)
    
    with _CACHE_LOCK:
        _LIBRARY_CACHE = sorted_library

    titles_lib.identification_in_progress_count -= 1
    titles_lib.unload_titledb()

    # Update library size metric
    total_size = sum(g.get('size', 0) for g in games_info)
    LIBRARY_SIZE.set(total_size)

    logger.info(f'Generating library done. Found {len(games_info)} games.')
    return sorted_library

def update_game_in_cache(title_id):
    """Update a single game in the memory and disk cache"""
    global _LIBRARY_CACHE
    
    # Ensure TitleDB is loaded
    titles_lib.load_titledb()
    
    # Get fresh data for this title
    title = Titles.query.options(joinedload(Titles.apps).joinedload(Apps.files)).filter_by(title_id=title_id).first()
    if not title:
        # If title no longer exists, remove from cache if present
        with _CACHE_LOCK:
            if _LIBRARY_CACHE:
                _LIBRARY_CACHE = [g for g in _LIBRARY_CACHE if g['id'] != title_id]
        return

    # Convert to the format expected by get_game_info_item
    title_data = to_dict(title)
    title_data['apps'] = []
    for a in title.apps:
        a_dict = to_dict(a)
        a_dict['files_info'] = [{'path': f.filepath, 'size': f.size} for f in a.files]
        title_data['apps'].append(a_dict)

    updated_game = get_game_info_item(title_id, title_data)

    with _CACHE_LOCK:
        if _LIBRARY_CACHE:
            # Find and update or add
            found = False
            for i, g in enumerate(_LIBRARY_CACHE):
                if g['id'] == title_id:
                    if updated_game:
                        _LIBRARY_CACHE[i] = updated_game
                    else:
                        _LIBRARY_CACHE.pop(i)
                    found = True
                    break
            
            if not found and updated_game:
                _LIBRARY_CACHE.append(updated_game)
                _LIBRARY_CACHE.sort(key=lambda x: x.get("name", "Unrecognized") or "Unrecognized")

            # Update disk cache too
            save_library_to_disk({
                'hash': compute_apps_hash(),
                'library': _LIBRARY_CACHE
            })
    
    titles_lib.unload_titledb()
