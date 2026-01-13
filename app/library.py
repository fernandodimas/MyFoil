import hashlib
from constants import *
from db import *
import titles as titles_lib
import datetime
from pathlib import Path
from utils import *

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
            
            logger.info(f"Removed library: {path}")
            if total_apps_updated > 0:
                logger.info(f"Updated {total_apps_updated} app entries to remove library file references.")
            if titles_removed > 0:
                logger.info(f"Removed {titles_removed} titles with no owned apps.")
        
        # Remove from settings
        success, errors = delete_library_path_from_settings(path)
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

        file_info = titles_lib.get_file_info(filepath)

        if file_info is None:
            logger.error(f'Failed to get info for file: {file} - file will be skipped.')
            # in the future save identification error to be displayed and inspected in the UI
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

        # Commit every 100 files to avoid excessive memory use
        if (n + 1) % 100 == 0:
            db.session.commit()

    # Final commit
    db.session.commit()

def scan_library_path(library_path):
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
                logger.warning(f'Identifying file ({n+1}/{nb_to_identify}): {filename} no longer exists, deleting from database.')
                Files.query.filter_by(id=file_id).delete(synchronize_session=False)
                continue

            logger.info(f'Identifying file ({n+1}/{nb_to_identify}): {filename}')
            identification, success, file_contents, error = titles_lib.identify_file(filepath)
            if success and file_contents and not error:
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
            version = str(version_info['version'])
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

    titles = get_all_titles()
    for n, title in enumerate(titles):
        have_base = False
        up_to_date = False
        complete = False

        title_id = title.title_id
        title_apps = get_all_title_apps(title_id)

        # check have_base - look for owned base apps
        owned_base_apps = [app for app in title_apps if app.get('app_type') == APP_TYPE_BASE and app.get('owned')]
        have_base = len(owned_base_apps) > 0

        # check up_to_date - find highest owned update version
        owned_update_apps = [app for app in title_apps if app.get('app_type') == APP_TYPE_UPD and app.get('owned')]
        available_update_apps = [app for app in title_apps if app.get('app_type') == APP_TYPE_UPD]
        
        if not available_update_apps:
            # No updates available, consider up to date
            up_to_date = True
        elif not owned_update_apps:
            # Updates available but none owned
            up_to_date = False
        else:
            # Find highest available version and highest owned version
            highest_available_version = max(int(app['app_version']) for app in available_update_apps)
            highest_owned_version = max(int(app['app_version']) for app in owned_update_apps)
            up_to_date = highest_owned_version >= highest_available_version

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

def generate_library():
    """Generate the game library grouped by TitleID, using cached version if unchanged"""
    if is_library_unchanged():
        saved_library = load_library_from_disk()
        if saved_library:
            return saved_library['library']
    
    logger.info(f'Generating library (grouped by Title)...')
    titles_lib.load_titledb()
    
    # Get all Titles known to the system
    all_titles = get_all_titles()
    games_info = []

    for title_obj in all_titles:
        tid = title_obj.title_id
        
        # Get all apps for this title (both owned and missing)
        all_title_apps = get_all_title_apps(tid)
        
        # We only show games that have at least one OWNED app in the library
        owned_apps = [a for a in all_title_apps if a.get('owned')]
        if not owned_apps:
            continue
            
        # Base info from TitleDB
        info = titles_lib.get_game_info(tid)
        if not info:
            info = {'name': f'Unknown ({tid})', 'iconUrl': '', 'publisher': 'Unknown'}
            
        game = info.copy()
        game['title_id'] = tid
        game['id'] = tid  # For display on card as game ID
        
        # Status indicators
        game['has_base'] = title_obj.have_base
        game['has_latest_version'] = title_obj.up_to_date
        game['has_all_dlcs'] = title_obj.complete
        
        # Determine status color for UI
        # Orange if missing updates or DLCs (for games with base)
        if game['has_base'] and (not game['has_latest_version'] or not game['has_all_dlcs']):
            game['status_color'] = 'orange'
        elif game['has_base']:
            game['status_color'] = 'green'
        else:
            game['status_color'] = 'gray'

        # Files and details
        game['base_files'] = []
        base_app_entries = [a for a in all_title_apps if a['app_type'] == APP_TYPE_BASE and a['owned']]
        for b in base_app_entries:
            if 'files' in b:
                game['base_files'].extend(b['files'])
        
        # Deduplicate files
        game['base_files'] = list(set(game['base_files']))

        # Updates details
        update_apps = [a for a in all_title_apps if a['app_type'] == APP_TYPE_UPD]
        available_versions = titles_lib.get_all_existing_versions(tid)
        version_release_dates = {v['version']: v['release_date'] for v in available_versions}
        
        version_list = []
        for upd in update_apps:
            v_int = int(upd['app_version'])
            version_list.append({
                'version': v_int,
                'owned': upd['owned'],
                'release_date': version_release_dates.get(v_int, 'Unknown'),
                'files': upd.get('files', []) if upd['owned'] else []
            })
        
        game['updates'] = sorted(version_list, key=lambda x: x['version'])
        game['latest_version_available'] = max([v['version'] for v in available_versions], default=0)
        game['owned_version'] = max([v['version'] for v in version_list if v['owned']], default=0)
        
        # For card display, use owned_version or 0
        game['display_version'] = f"v{game['owned_version']}" if game['owned_version'] > 0 else "Base"

        # DLC details
        # Group DLCs by their unique app_id (a game can have many DLCs)
        dlcs_by_id = {}
        all_possible_dlc_ids = titles_lib.get_all_existing_dlc(tid)
        
        # First, track what we KNOW exists from TitleDB
        for dlc_id in all_possible_dlc_ids:
            dlcs_by_id[dlc_id] = {
                'app_id': dlc_id,
                'name': titles_lib.get_game_info(dlc_id).get('name', f'DLC {dlc_id}'),
                'owned': False,
                'latest_version': 0,
                'owned_version': 0
            }
            
        # Now fill in with what we have in DB
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
        
        games_info.append(game)
    
    library_data = {
        'hash': compute_apps_hash(),
        'library': sorted(games_info, key=lambda x: x.get("name", "Unrecognized") or "Unrecognized")
    }

    save_library_to_disk(library_data)

    titles_lib.identification_in_progress_count -= 1
    titles_lib.unload_titledb()

    logger.info(f'Generating library done. Found {len(games_info)} games.')

    return library_data['library']
