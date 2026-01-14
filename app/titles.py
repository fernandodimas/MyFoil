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
_versions_db = None
_loaded_titles_file = None  # Track which titles file was loaded

def get_titles_count():
    global _titles_db
    return len(_titles_db) if _titles_db else 0


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

    # Try 1: Standard load - fast and correct
    try:
        data = json.loads(content)
        return data if not isinstance(data, dict) else (data.get('data') or data.get('items') or data.get('titles') or data)
    except json.JSONDecodeError:
        pass

    # Try 2: More aggressive sanitization for escape sequences
    logger.warning(f"JSON error in {filepath}, attempting aggressive sanitization...")
    try:
        # Pattern to match a valid escape or a bare backslash
        # Group 1 captures valid escape sequences: \", \\, \/, \b, \f, \n, \r, \t, or \uXXXX
        pattern = re.compile(r'(\\([\"\\/bfnrt]|u[0-9a-fA-F]{4}))|(\\)')
        
        def replace_func(m):
            if m.group(1):
                return m.group(1) # Valid escape, keep it
            else:
                return r'\\' # Bare backslash, escape it

        sanitized = pattern.sub(replace_func, content)
        
        # Strip ALL non-printable control characters except whitespace
        sanitized = "".join(ch for ch in sanitized if ord(ch) >= 32 or ch in '\n\r\t')
        
        # Try loading the sanitized version
        data = json.loads(sanitized, strict=False)
        return data if not isinstance(data, dict) else (data.get('data') or data.get('items') or data.get('titles') or data)
    except Exception as e:
        logger.error(f"Aggressive sanitization failed for {filepath}: {e}")

    # Try 3: Nuclear Cleanup - if still failing, it's likely structural or has nested escape issues
    try:
        # Bruteforce: replace all \ with \\ then restore common escapes
        # This fixes bare backslashes but we MUST restore valid sequences or it will remain invalid
        nuclear = content.replace('\\', '\\\\')
        for escape in ['"', '\\', '/', 'b', 'f', 'n', 'r', 't']:
            nuclear = nuclear.replace('\\\\' + escape, '\\' + escape)
        # Restore unicode
        nuclear = re.sub(r'\\\\u([0-9a-fA-F]{4})', r'\\u\1', nuclear)
        
        nuclear = "".join(ch for ch in nuclear if ord(ch) >= 32 or ch in '\n\r\t')
        data = json.loads(nuclear, strict=False)
        return data if not isinstance(data, dict) else (data.get('data') or data.get('items') or data.get('titles') or data)
    except Exception as e:
        logger.error(f"Nuclear cleanup failed for {filepath}: {e}")
            
    except:
        pass

    # Try 5: Chunked Recovery (Absolute Last Resort)
    # If the file is so corrupted it has binary garbage or missing structural chars
    # we can try to recover individual game objects one by one using Regex.
    logger.warning(f"Whole-file parsing failed for {filepath}. Attempting chunked recovery...")
    try:
        recovered = {}
        # Pattern for "TitleID": { ... }
        # Matches 16 hex characters as a key
        pattern = re.compile(r'\"([0-9A-F]{16})\":\s*\{')
        
        # We need the full content for this
        parts = pattern.split(content)
        # parts[0] is garbage or opening brace
        # parts[1] is ID, parts[2] is Body, etc.
        
        for i in range(1, len(parts), 2):
            tid = parts[i]
            body = parts[i+1]
            
            # Find the end of this object (the last closing brace)
            last_brace = body.rfind('}')
            if last_brace != -1:
                clean_body = '{' + body[:last_brace+1]
                try:
                    # Try to parse this individual object
                    obj = json.loads(clean_body, strict=False)
                    recovered[tid] = obj
                except:
                    # Partial cleanup for the chunk
                    try:
                        # Basic escape fix for the chunk
                        chunk_sanitized = re.sub(r'\\(?!(["\\/bfnrt]|u[0-9a-fA-F]{4}))', r'\\\\', clean_body)
                        obj = json.loads(chunk_sanitized, strict=False)
                        recovered[tid] = obj
                    except:
                        continue # Skip this specific corrupt entry
        
        if len(recovered) > 0:
            logger.info(f"Chunked recovery successful! Salvaged {len(recovered)} entries from corrupted file {filepath}.")
            return recovered
    except Exception as e:
        logger.error(f"Chunked recovery failed for {filepath}: {e}")

    return None

def getDirsAndFiles(path):
    entries = os.listdir(path)
    allFiles = []
    allDirs = []

    for entry in entries:
        if entry.startswith('._'):
            continue
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
        
        # Database fallback chain: Region -> US/en -> Generic titles.json
        region = app_settings['titles'].get('region', 'US')
        language = app_settings['titles'].get('language', 'en')
        possible_files = titledb.get_region_titles_filenames(region, language) + ["titles.US.en.json", "US.en.json", "titles.json"]
        
        _titles_db = {}
        global _loaded_titles_file
        _loaded_titles_file = [] # Now a list of files loaded
        
        # Load order: Basic titles.json -> Region specific (reverses possible_files)
        # We want to load the most "generic" first and OVERWRITE with the most "specific"
        load_order = ["titles.json", "US.en.json", "titles.US.en.json"]
        # Add regional files at the end of the load order so they take priority
        for f in possible_files:
            if f not in load_order:
                load_order.append(f)
        
        # Always load custom.json last to allow manual overrides
        load_order.append("custom.json")

        for filename in load_order:
            filepath = os.path.join(TITLEDB_DIR, filename)
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                logger.info(f"Loading TitleDB: {filename}...")
                loaded = robust_json_load(filepath)
                if loaded:
                    count = len(loaded) if isinstance(loaded, (dict, list)) else 0
                    if count > 0:
                        # Convert list to dict if necessary for merging
                        current_batch = {}
                        if isinstance(loaded, list):
                            for item in loaded:
                                if isinstance(item, dict) and 'id' in item:
                                    current_batch[item['id'].upper()] = item
                        else:
                            current_batch = {k.upper(): v for k, v in loaded.items() if isinstance(v, dict)}
                        
                        # MERGE logic: Keep metadata (urls, size, etc) but update names/descriptions
                        if not _titles_db:
                            _titles_db = current_batch
                        else:
                            for tid, data in current_batch.items():
                                if tid in _titles_db:
                                    # Override specific fields but keep the rest
                                    for field in ['name', 'description', 'bannerUrl', 'iconUrl', 'publisher', 'releaseDate', 'size', 'category']:
                                        if data.get(field):
                                            _titles_db[tid][field] = data[field]
                                else:
                                    _titles_db[tid] = data
                        
                        _loaded_titles_file.append(filename)
                        logger.info(f"SUCCESS: Merged {count} items from {filename}")
                else:
                    logger.warning(f"Could not parse {filename}, skipping...")
        
        if _titles_db:
            # INDEXING: Ensure TitleDB is indexed by TitleID for O(1) lookups
            indexed_db = {}
            logger.info(f"Indexing TitleDB by TitleID...")
            
            items = []
            if isinstance(_titles_db, dict):
                items = _titles_db.values()
                # Also include keys if they look like TitleIDs (Fallback)
                for k, v in _titles_db.items():
                    if len(k) == 16 and isinstance(v, dict):
                        tid = k.upper()
                        if tid not in indexed_db or not indexed_db[tid].get('name'):
                            indexed_db[tid] = v
            elif isinstance(_titles_db, list):
                items = _titles_db
            
            for item in items:
                if isinstance(item, dict):
                    tid = str(item.get('id', '')).upper()
                    if len(tid) == 16:
                        # Only overwrite if we have a name (don't let empty entries from titles.json overwrite good ones)
                        if tid not in indexed_db or (item.get('name') and not indexed_db[tid].get('name')):
                            indexed_db[tid] = item
            
            _titles_db = indexed_db
            logger.info(f"TitleDB indexed. Total unique TitleIDs: {len(_titles_db)}")

        if not _titles_db:
            logger.error("CRITICAL: Failed to load any TitleDB. Game identification will be limited.")
            _titles_db = {}

        _versions_db = robust_json_load(os.path.join(TITLEDB_DIR, 'versions.json')) or {}
        _cnmts_db = _cnmts_db or {}

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
        load_titledb()
    
    if not _titles_db:
        return {
            'name': f'Unknown ({title_id})',
            'bannerUrl': '',
            'iconUrl': '',
            'id': title_id,
            'category': [],
            'releaseDate': '',
            'size': 0,
            'publisher': '--',
            'description': 'Database not loaded. Please update TitleDB in settings.'
        }



    try:
        info = None
        search_id = str(title_id).upper()

        if not _titles_db:
            logger.warning(f"TitleDB not loaded for lookup of {search_id}")
        else:
            if _titles_db:
                info = _titles_db.get(search_id)
                if not info:
                    # Case-insensitive fallback
                    info = _titles_db.get(search_id.upper()) or _titles_db.get(search_id.lower())

        if info:
            res = {
                'name': info.get('name') or 'Unknown Title',
                'bannerUrl': info.get('bannerUrl') or '',
                'iconUrl': info.get('iconUrl') or '',
                'id': info.get('id') or title_id,
                'category': info.get('category', []) if isinstance(info.get('category'), list) else [info.get('category')] if info.get('category') else [],
                'release_date': info.get('releaseDate') or '',
                'size': info.get('size') or 0,
                'publisher': info.get('publisher') or 'Nintendo',
                'description': info.get('description') or ''
            }
            
            # DLC/Update Icon Fallback: If icon is missing, try to inherit from base game
            if (not res['iconUrl'] or res['iconUrl'] == '') and not search_id.endswith('000'):
                possible_base_ids = [search_id[:-3] + '000']
                try:
                    # For DLCs, the base ID is often (DLC_PREFIX - 1) + 000
                    prefix = search_id[:-3]
                    base_prefix = hex(int(prefix, 16) - 1)[2:].upper().rjust(13, '0')
                    possible_base_ids.append(base_prefix + '000')
                except:
                    pass
                
                for bid in possible_base_ids:
                    base_info = get_game_info(bid)
                    if base_info and base_info.get('iconUrl') and not base_info['name'].startswith('Unknown'):
                        res['iconUrl'] = base_info['iconUrl']
                        res['bannerUrl'] = res['bannerUrl'] or base_info.get('bannerUrl')
                        logger.debug(f"Inherited visuals from base game {bid} for {search_id}")
                        break
            
            # Fallback: Use Banner as Icon if Icon is still missing
            if (not res['iconUrl'] or res['iconUrl'] == '') and res['bannerUrl']:
                res['iconUrl'] = res['bannerUrl']
            
            return res
        
        # If not found, try to find parent BASE game if this is a DLC/UPD
        if not search_id.endswith('000'):
            possible_base_ids = [search_id[:-3] + '000']
            try:
                prefix = search_id[:-3]
                base_prefix = hex(int(prefix, 16) - 1)[2:].upper().rjust(13, '0')
                possible_base_ids.append(base_prefix + '000')
            except:
                pass

            for bid in possible_base_ids:
                logger.debug(f"ID {search_id} not found, attempting fallback to base {bid}")
                base_info = get_game_info(bid)
                if base_info and not base_info['name'].startswith('Unknown'):
                    return {
                        'name': f"{base_info['name']} [DLC/UPD]",
                        'bannerUrl': base_info['bannerUrl'],
                        'iconUrl': base_info['iconUrl'],
                        'id': title_id,
                        'category': base_info['category'],
                        'release_date': base_info['release_date'],
                        'size': 0,
                        'publisher': base_info['publisher'],
                        'description': f"Informação estendida do jogo base: {base_info['name']}"
                    }

        raise Exception(f"ID {search_id} not found in database")
    except Exception as e:
        logger.debug(f"Identification failed for {title_id}: {e}")
        return {
            'name': f'Unknown ({title_id})',
            'bannerUrl': '',
            'iconUrl': '',
            'id': title_id.upper(),
            'category': [],
            'release_date': '',
            'size': 0,
            'publisher': '--',
            'description': 'ID não encontrado no banco de dados. Por favor, atualize o TitleDB nas configurações.'
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
    versions_dict = {} # Key: version_int, Value: release_date

    # Priority 1: JSON Versions DB (Full History)
    if _versions_db and titleid in _versions_db:
        for v_str, release_date in _versions_db[titleid].items():
            try:
                versions_dict[int(v_str)] = release_date
            except:
                continue
    
    if not versions_dict:
        return []

    # Convert back to list format expected by caller
    return [
        {
            'version': v,
            'update_number': get_update_number(v),
            'release_date': rd,
        }
        for v, rd in sorted(versions_dict.items())
    ]

    return []

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
    
    app_id = app_id.lower()
    if app_id in _versions_txt_db:
        return _versions_txt_db[app_id]
    return None

def get_loaded_titles_file():
    global _loaded_titles_file
    if isinstance(_loaded_titles_file, list):
        # Prefer showing the most specific/regional file if multiple were merged
        # The regional ones are at the end of the load_order
        for f in reversed(_loaded_titles_file):
            if '.' in f and any(ext in f.lower() for ext in ['.br', 'pt', 'pt.json', 'br.json']):
                return f
        return _loaded_titles_file[-1] if _loaded_titles_file else "None"
    return _loaded_titles_file or "None"
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

def get_loaded_titles_file():
    """Return the filename of the currently loaded titles database"""
    global _loaded_titles_file
    return _loaded_titles_file

def get_custom_title_info(title_id):
    """Retrieve custom info for a specific TitleID from custom.json"""
    custom_path = os.path.join(TITLEDB_DIR, 'custom.json')
    custom_db = robust_json_load(custom_path) or {}
    return custom_db.get(title_id.upper())

def save_custom_title_info(title_id, data):
    """
    Save custom info for a TitleID to custom.json and update in-memory DB.
    data should contain: name, description, publisher, iconUrl, bannerUrl, ...
    """
    global _titles_db
    title_id = title_id.upper()
    
    custom_path = os.path.join(TITLEDB_DIR, 'custom.json')
    
    # 1. Load existing custom DB
    custom_db = robust_json_load(custom_path) or {}
    
    # 2. Update entry
    # Ensure ID is present in data
    data['id'] = title_id
    
    if title_id in custom_db:
        custom_db[title_id].update(data)
    else:
        custom_db[title_id] = data
        
    # 3. Write back to disk
    try:
        with open(custom_path, 'w', encoding='utf-8') as f:
            json.dump(custom_db, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save custom.json: {e}")
        return False, str(e)

    # 4. Update in-memory DB immediately
    if _titles_db:
        if title_id in _titles_db:
            _titles_db[title_id].update(data)
        else:
            _titles_db[title_id] = data
            
    return True, None

def search_titledb_by_name(query):
    """Search for games in the loaded TitleDB by name."""
    global _titles_db
    if not _titles_db:
        return []
        
    results = []
    query = query.lower()
    
    # Simple iteration - could be optimized with an index if needed but for <20k items it's fine
    for tid, data in _titles_db.items():
        name = data.get('name', '')
        if name and query in name.lower():
            results.append({
                'id': tid,
                'name': name,
                'region': data.get('region', '--'),
                'iconUrl': data.get('iconUrl'),
                'bannerUrl': data.get('bannerUrl'),
                'publisher': data.get('publisher'),
                'description': data.get('description')
            })
            if len(results) >= 50: break
            
    return results
