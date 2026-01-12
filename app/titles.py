import os
import sys
import re
import json

import titledb
from constants import *
from utils import *
from settings import *
from pathlib import Path
from binascii import hexlify as hx, unhexlify as uhx
import logging

from nstools.Fs import Pfs0, Nca, Type, factory
from nstools.lib import FsTools
from nstools.nut import Keys

# Retrieve main logger
logger = logging.getLogger('main')

Pfs0.Print.silent = True

app_id_regex = r"\[([0-9A-Fa-f]{16})\]"
version_regex = r"\[v(\d+)\]"

# Global variables for TitleDB data
identification_in_progress_count = 0
_titles_db_loaded = False
_cnmts_db = None
_titles_db = None
_versions_db = None
_versions_txt_db = None

def robust_json_load(filepath):
    """Reliably load JSON files even with invalid escape sequences or control characters."""
    if not os.path.exists(filepath):
        return None
        
    try:
        with open(filepath, encoding='utf-8', errors='ignore') as f:
            content = f.read()
            if not content:
                return None
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")
        return None

    try:
        # First try: Standard load
        return json.loads(content)
    except json.JSONDecodeError as e:
        # If it's an escape error, try to fix backslashes
        if 'Invalid \\escape' in str(e):
            logger.warning(f"Invalid escape found in {filepath}, attempting to sanitize...")
            # Escape backslashes that aren't part of a valid JSON escape sequence
            sanitized = re.sub(r'\\(?![u"\\\/bfnrt])', r'\\\\', content)
            try:
                return json.loads(sanitized, strict=False)
            except Exception as ex:
                logger.error(f"Sanitization failed for {filepath}: {ex}")
        
        # Second try: Non-strict load
        try:
            return json.loads(content, strict=False)
        except Exception as ex:
            logger.error(f"Critical error parsing JSON {filepath}: {ex}")
            return None

def getDirsAndFiles(path):
    entries = os.listdir(path)
    allFiles = []
    allDirs = []

    for entry in entries:
        fullPath = os.path.join(path, entry)
        if os.path.isdir(fullPath):
            allDirs.append(fullPath)
            dirs, files = getDirsAndFiles(fullPath)
            allDirs += dirs
            allFiles += files
        elif fullPath.split('.')[-1] in ALLOWED_EXTENSIONS:
            allFiles.append(fullPath)
    return allDirs, allFiles

def get_app_id_from_filename(filename):
    app_id_match = re.search(app_id_regex, filename)
    return app_id_match[1] if app_id_match is not None else None

def get_version_from_filename(filename):
    version_match = re.search(version_regex, filename)
    return version_match[1] if version_match is not None else None

def get_title_id_from_app_id(app_id, app_type):
    base_id = app_id[:-3]
    if app_type == APP_TYPE_UPD:
        title_id = base_id + '000'
    elif app_type == APP_TYPE_DLC:
        title_id = hex(int(base_id, base=16) - 1)[2:].rjust(len(base_id), '0') + '000'
    return title_id.upper()

def get_file_size(filepath):
    return os.path.getsize(filepath)

def get_file_info(filepath):
    filedir, filename = os.path.split(filepath)
    extension = filename.split('.')[-1]
    
    compressed = False
    if extension in ['nsz', 'xcz']:
        compressed = True

    return {
        'filepath': filepath,
        'filedir': filedir,
        'filename': filename,
        'extension': extension,
        'compressed': compressed,
        'size': get_file_size(filepath),
    }

def identify_appId(app_id):
    app_id = app_id.lower()
    
    global _cnmts_db
    if _cnmts_db is None:
        logger.error("cnmts_db is not loaded. Call load_titledb first.")
        return None, None

    if app_id in _cnmts_db:
        app_id_keys = list(_cnmts_db[app_id].keys())
        if len(app_id_keys):
            app = _cnmts_db[app_id][app_id_keys[-1]]
            
            if app['titleType'] == 128:
                app_type = APP_TYPE_BASE
                title_id = app_id.upper()
            elif app['titleType'] == 129:
                app_type = APP_TYPE_UPD
                if 'otherApplicationId' in app:
                    title_id = app['otherApplicationId'].upper()
                else:
                    title_id = get_title_id_from_app_id(app_id, app_type)
            elif app['titleType'] == 130:
                app_type = APP_TYPE_DLC
                if 'otherApplicationId' in app:
                    title_id = app['otherApplicationId'].upper()
                else:
                    title_id = get_title_id_from_app_id(app_id, app_type)
        else:
            logger.warning(f'{app_id} has no keys in cnmts_db, fallback to default identification.')
            if app_id.endswith('000'):
                app_type = APP_TYPE_BASE
                title_id = app_id
            elif app_id.endswith('800'):
                app_type = APP_TYPE_UPD
                title_id = get_title_id_from_app_id(app_id, app_type)
            else:
                app_type = APP_TYPE_DLC
                title_id = get_title_id_from_app_id(app_id, app_type)
    else:
        logger.warning(f'{app_id} not in cnmts_db, fallback to default identification.')
        if app_id.endswith('000'):
            app_type = APP_TYPE_BASE
            title_id = app_id
        elif app_id.endswith('800'):
            app_type = APP_TYPE_UPD
            title_id = get_title_id_from_app_id(app_id, app_type)
        else:
            app_type = APP_TYPE_DLC
            title_id = get_title_id_from_app_id(app_id, app_type)
    
    return title_id.upper(), app_type

def load_titledb(force=False):
    global _cnmts_db
    global _titles_db
    global _versions_db
    global _versions_txt_db
    global identification_in_progress_count
    global _titles_db_loaded

    identification_in_progress_count += 1
    if force:
        _titles_db_loaded = False

    if not _titles_db_loaded:
        logger.info("Loading TitleDBs into memory...")
        
        # Diagnostic: List files in TitleDB dir
        try:
            files = os.listdir(TITLEDB_DIR)
            logger.info(f"Files in TitleDB directory: {', '.join(files)}")
        except Exception as e:
            logger.warning(f"Could not list TitleDB directory: {e}")

        app_settings = load_settings()
        
        _cnmts_db = robust_json_load(os.path.join(TITLEDB_DIR, 'cnmts.json'))
        
        # Try region file, then US/en, then generic titles.json
        region_file = titledb.get_region_titles_file(app_settings)
        possible_files = [region_file, "titles.US.en.json", "titles.json"]
        
        _titles_db = {}
        for filename in possible_files:
            filepath = os.path.join(TITLEDB_DIR, filename)
            if os.path.exists(filepath):
                logger.info(f"Loading titles from {filename}...")
                _titles_db = robust_json_load(filepath)
                if _titles_db:
                    break
        
        if not _titles_db:
            logger.warning("No titles database found among possible files!")
        else:
            count = len(_titles_db) if isinstance(_titles_db, (dict, list)) else 0
            logger.info(f"TitleDBs loaded. ({count} titles in memory)")

        _versions_db = robust_json_load(os.path.join(TITLEDB_DIR, 'versions.json'))

        _versions_txt_db = {}
        try:
            with open(os.path.join(TITLEDB_DIR, 'versions.txt'), encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line_strip = line.rstrip("\n")
                    if '|' in line_strip:
                        parts = line_strip.split('|')
                        if len(parts) >= 3:
                            app_id, rightsId, version = parts[0], parts[1], parts[2]
                            if not version:
                                version = "0"
                            _versions_txt_db[app_id] = version
        except Exception as e:
            logger.warning(f"Error loading versions.txt: {e}")

        _titles_db_loaded = True
        logger.info("TitleDBs loaded.")

@debounce(30)
def unload_titledb():
    global _cnmts_db
    global _titles_db
    global _versions_db
    global _versions_txt_db
    global identification_in_progress_count
    global _titles_db_loaded

    if identification_in_progress_count:
        logger.debug('Identification still in progress, not unloading TitleDB.')
        return

    logger.info("Unloading TitleDBs from memory...")
    _cnmts_db = None
    _titles_db = None
    _versions_db = None
    _versions_txt_db = None
    _titles_db_loaded = False
    logger.info("TitleDBs unloaded.")

def identify_file_from_filename(filename):
    title_id = None
    app_id = None
    app_type = None
    version = None
    errors = []

    app_id = get_app_id_from_filename(filename)
    if app_id is None:
        errors.append('Could not determine App ID from filename, pattern [APPID] not found. Title ID and Type cannot be derived.')
    else:
        title_id, app_type = identify_appId(app_id)

    version = get_version_from_filename(filename)
    if version is None:
        errors.append('Could not determine version from filename, pattern [vVERSION] not found.')
    
    error = ' '.join(errors)
    return app_id, title_id, app_type, version, error
    
def identify_file_from_cnmt(filepath):
    contents = []
    titleId = None
    version = None
    titleType = None
    container = factory(Path(filepath).resolve())
    container.open(filepath, 'rb')
    if filepath.lower().endswith(('.xci', '.xcz')):
        container = container.hfs0['secure']
    try:
        for nspf in container:
            if isinstance(nspf, Nca.Nca) and nspf.header.contentType == Type.Content.META:
                for section in nspf:
                    if isinstance(section, Pfs0.Pfs0):
                        Cnmt = section.getCnmt()
                        
                        titleType = FsTools.parse_cnmt_type_n(hx(Cnmt.titleType.to_bytes(length=(min(Cnmt.titleType.bit_length(), 1) + 7) // 8, byteorder = 'big')))
                        if titleType == 'GAME':
                            titleType = APP_TYPE_BASE
                        titleId = Cnmt.titleId.upper()
                        version = Cnmt.version
                        contents.append((titleType, titleId, version))
                        # print(f'\n:: CNMT: {Cnmt._path}\n')
                        # print(f'Title ID: {titleId}')
                        # print(f'Version: {version}')
                        # print(f'Title Type: {titleType}')
                        # print(f'Title ID: {titleId} Title Type: {titleType} Version: {version} ')

    finally:
        container.close()

    return contents

def identify_file(filepath):
    filename = os.path.split(filepath)[-1]
    contents = []
    success = True
    error = ''
    if Keys.keys_loaded:
        identification = 'cnmt'
        try:
            cnmt_contents = identify_file_from_cnmt(filepath)
            if not cnmt_contents:
                error = 'No content found in NCA containers.'
                success = False
            else:
                for content in cnmt_contents:
                    app_type, app_id, version = content
                    if app_type != APP_TYPE_BASE:
                        # need to get the title ID from cnmts
                        title_id, app_type = identify_appId(app_id)
                    else:
                        title_id = app_id
                    contents.append((title_id, app_type, app_id, version))
        except Exception as e:
            logger.error(f'Could not identify file {filepath} from metadata: {e}')
            error = str(e)
            success = False

    else:
        identification = 'filename'
        app_id, title_id, app_type, version, error = identify_file_from_filename(filename)
        if not error:
            contents.append((title_id, app_type, app_id, version))
        else:
            success = False

    if contents:
        contents = [{
            'title_id': c[0],
            'app_id': c[2],
            'type': c[1],
            'version': c[3],
            } for c in contents]
    
    # IMPORTANT: Even if keys failed, we still want to return a result 
    # if filename identification worked
    if not contents and not success:
        # Fallback to filename identification if CNMT failed
        app_id, title_id, app_type, version, error = identify_file_from_filename(filename)
        if title_id:
            contents = [{
                'title_id': title_id,
                'app_id': app_id,
                'type': app_type,
                'version': version,
            }]
            identification = 'filename'
            success = True # Consider it a success if we got something from filename

    return identification, success, contents, error


def get_game_info(title_id):
    global _titles_db
    if not _titles_db:
        logger.error("titles_db is empty or not loaded.")
        return {
            'name': 'Unrecognized (No DB)',
            'bannerUrl': '//placehold.it/400x200',
            'iconUrl': '',
            'id': title_id,
            'category': '',
        }

    try:
        info = None
        search_id = title_id.upper()

        if isinstance(_titles_db, dict):
            # Format A: { "ID": { "name": "..." } }
            info = _titles_db.get(search_id) or _titles_db.get(search_id.lower())
            
            # Format B: { "some_key": { "id": "ID", "name": "..." } }
            if not info:
                for k, v in _titles_db.items():
                    if isinstance(v, dict) and v.get('id', '').upper() == search_id:
                        info = v
                        break
        
        elif isinstance(_titles_db, list):
            # Format C: [ { "id": "ID", "name": "..." }, ... ]
            for item in _titles_db:
                if isinstance(item, dict) and item.get('id', '').upper() == search_id:
                    info = item
                    break

        if info:
            return {
                'name': info.get('name', 'Unrecognized'),
                'bannerUrl': info.get('bannerUrl', '//placehold.it/400x200'),
                'iconUrl': info.get('iconUrl', ''),
                'id': info.get('id', title_id),
                'category': info.get('category', ''),
            }
        
        raise Exception(f"ID {search_id} not found in database")
    except Exception as e:
        logger.debug(f"Identification failed for {title_id}: {e}")
        return {
            'name': 'Unrecognized',
            'bannerUrl': '//placehold.it/400x200',
            'iconUrl': '',
            'id': title_id,
            'category': '',
        }

def get_update_number(version):
    return int(version)//65536

def get_game_latest_version(all_existing_versions):
    return max(v['version'] for v in all_existing_versions)

def get_all_existing_versions(titleid):
    global _versions_db
    if _versions_db is None:
        logger.error("versions_db is not loaded. Call load_titledb first.")
        return []

    titleid = titleid.lower()
    if titleid not in _versions_db:
        # print(f'Title ID not in versions.json: {titleid.upper()}')
        return []

    versions_from_db = _versions_db[titleid].keys()
    return [
        {
            'version': int(version_from_db),
            'update_number': get_update_number(version_from_db),
            'release_date': _versions_db[titleid][str(version_from_db)],
        }
        for version_from_db in versions_from_db
    ]

def get_all_app_existing_versions(app_id):
    global _cnmts_db
    if _cnmts_db is None:
        logger.error("cnmts_db is not loaded. Call load_titledb first.")
        return None

    app_id = app_id.lower()
    if app_id in _cnmts_db:
        versions_from_cnmts_db = _cnmts_db[app_id].keys()
        if len(versions_from_cnmts_db):
            return sorted(versions_from_cnmts_db)
        else:
            logger.warning(f'No keys in cnmts.json for app ID: {app_id.upper()}')
            return None
    else:
        # print(f'DLC app ID not in cnmts.json: {app_id.upper()}')
        return None
    
def get_app_id_version_from_versions_txt(app_id):
    global _versions_txt_db
    if _versions_txt_db is None:
        logger.error("versions_txt_db is not loaded. Call load_titledb first.")
        return None
    return _versions_txt_db.get(app_id, None)
    
def get_all_existing_dlc(title_id):
    global _cnmts_db
    if _cnmts_db is None:
        logger.error("cnmts_db is not loaded. Call load_titledb first.")
        return []

    title_id = title_id.lower()
    dlcs = []
    for app_id in _cnmts_db.keys():
        for version, version_description in _cnmts_db[app_id].items():
            if version_description.get('titleType') == 130 and version_description.get('otherApplicationId') == title_id:
                if app_id.upper() not in dlcs:
                    dlcs.append(app_id.upper())
    return dlcs
