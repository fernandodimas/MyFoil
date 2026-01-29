import os
import re
import json
import time
import datetime

import titledb
from constants import *
from utils import *
from settings import *
from pathlib import Path
from binascii import hexlify as hx
import logging

from nstools.Fs import Pfs0, Nca, Type, factory
from nstools.lib import FsTools
from nstools.nut import Keys

# Retrieve main logger
logger = logging.getLogger("main")

Pfs0.Print.silent = True

app_id_regex = r"\[([0-9A-Fa-f]{16})\]"
version_regex = r"\[v(\d+)\]"


def format_release_date(date_input):
    """Formata data para padrão YYYY-MM-DD"""
    if not date_input:
        return ""

    date_str = str(date_input).strip()

    # Já está no formato correto
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str

    # Formato YYYYMMDD
    if re.match(r"^\d{8}$", date_str):
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

    # Tentar parsear outros formatos
    for fmt in ["%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d"]:
        try:
            parsed = datetime.datetime.strptime(date_str, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return date_str


# Global variables for TitleDB data
identification_in_progress_count = 0
_titles_db_loaded = False
_cnmts_db = None
_titles_db = None
_versions_db = None
_versions_db = None
_loaded_titles_file = None  # Track which titles file was loaded
_titledb_cache_timestamp = None  # Timestamp when TitleDB is last loaded
_titledb_cache_ttl = 3600  # TTL in seconds (1 hour default)


def get_titles_count():
    global _titles_db
    return len(_titles_db) if _titles_db else 0


# Database cache functions for TitleDB
def load_titledb_from_db():
    """Load TitleDB data from database cache if available and valid."""
    global _titles_db, _versions_db, _cnmts_db, _dlc_map, _titledb_cache_timestamp, _titles_db_loaded

    try:
        from db import TitleDBCache, TitleDBVersions, TitleDBDLCs

        # Check if cache tables exist
        try:
            cache_count = TitleDBCache.query.count()
            if cache_count == 0:
                logger.info("TitleDB cache is empty, will load from files")
                return False
        except Exception:
            logger.warning("TitleDB cache tables don't exist yet")
            return False

        # Load titles from cache
        logger.info(f"Loading TitleDB from database cache ({cache_count} titles)...")
        cached_titles = TitleDBCache.query.all()

        _titles_db = {}
        for entry in cached_titles:
            _titles_db[entry.title_id.upper()] = entry.data

        # Load versions from cache
        cached_versions = TitleDBVersions.query.all()
        _versions_db = {}
        for entry in cached_versions:
            tid = entry.title_id.lower()
            if tid not in _versions_db:
                _versions_db[tid] = {}
            _versions_db[tid][str(entry.version)] = entry.release_date

        # Load DLCs from cache and build index + REVERSE MAP
        _cnmts_db = {}
        _dlc_map = {}
        cached_dlcs = TitleDBDLCs.query.all()
        for entry in cached_dlcs:
            base_tid = entry.base_title_id.lower()
            dlc_app_id = entry.dlc_app_id.upper()

            # Build CNMT-style structure for compatibility
            if base_tid not in _cnmts_db:
                _cnmts_db[base_tid] = {}
            _cnmts_db[base_tid][dlc_app_id] = {
                "titleType": 130,  # DLC type
                "otherApplicationId": base_tid,
            }
            # Populate reverse map
            _dlc_map[dlc_app_id] = base_tid

        _titles_db_loaded = True
        _titledb_cache_timestamp = time.time()
        logger.info(
            f"TitleDB loaded from DB cache: {len(_titles_db)} titles, {len(_versions_db)} versions, {len(cached_dlcs)} DLCs"
        )
        return True

    except Exception as e:
        logger.error(f"Error loading TitleDB from cache: {e}")
        return False


def save_titledb_to_db(source_files, app_context=None):
    """Save TitleDB data to database cache for fast loading."""
    global _titles_db, _versions_db, _cnmts_db, _titledb_cache_timestamp

    try:
        from flask import has_app_context

        if not has_app_context():
            logger.warning("Cannot save TitleDB cache: no app context")
            return False

        from db import db, TitleDBCache, TitleDBVersions, TitleDBDLCs

        logger.info("Saving TitleDB to database cache...")

        now = datetime.datetime.now()

        # Clear old cache entries - use raw execution for speed and reliability
        try:
            db.session.execute(db.text("DELETE FROM titledb_cache"))
            db.session.execute(db.text("DELETE FROM titledb_versions"))
            db.session.execute(db.text("DELETE FROM titledb_dlcs"))
            db.session.commit()
        except Exception as e:
            logger.warning(f"Could not clear old cache via delete: {e}")
            db.session.rollback()

        # Try to import gevent for cooperative multitasking
        try:
            import gevent
        except ImportError:
            gevent = None

        # Deduplicate titles just in case (though dict keys should be unique)
        seen_titles = set()
        pending_entries = []
        BATCH_SIZE = 2000

        # Iterate and save in chunks to keep memory usage low
        for i, (tid, data) in enumerate(_titles_db.items()):
            # Yield to event loop every 50 items to prevent blocking heartbeat
            if gevent and i % 50 == 0:
                gevent.sleep(0.001)

            tid_upper = tid.upper()
            if tid_upper in seen_titles:
                continue
            seen_titles.add(tid_upper)

            pending_entries.append(
                TitleDBCache(
                    title_id=tid_upper,
                    data=data,
                    source=source_files.get(tid.lower(), "titles.json"),
                    downloaded_at=now,
                    updated_at=now,
                )
            )

            if len(pending_entries) >= BATCH_SIZE:
                db.session.bulk_save_objects(pending_entries)
                db.session.commit()
                pending_entries = []  # Release memory

                # Yield after DB commit
                if gevent:
                    gevent.sleep(0.01)

        # Save remaining entries
        title_count = len(seen_titles)
        if pending_entries:
            db.session.bulk_save_objects(pending_entries)
            db.session.commit()
            pending_entries = []

        # Batch insert versions
        version_entries = []
        # ... logic for versions ...

        # Deduplicate versions
        seen_versions = set()  # (tid, version)

        # Safe iteration with yield
        version_items = list((_versions_db or {}).items())
        for i, (tid, versions) in enumerate(version_items):
            if gevent and i % 50 == 0:
                gevent.sleep(0.001)

            tid_upper = tid.upper()
            for version_str, release_date in versions.items():
                try:
                    v_int = int(version_str)
                    if (tid_upper, v_int) in seen_versions:
                        continue
                    seen_versions.add((tid_upper, v_int))

                    version_entries.append(
                        TitleDBVersions(title_id=tid_upper, version=v_int, release_date=release_date)
                    )

                    if len(version_entries) >= BATCH_SIZE * 2:  # 4000 items
                        db.session.bulk_save_objects(version_entries)
                        db.session.commit()
                        version_entries = []
                        if gevent:
                            gevent.sleep(0.01)
                except (ValueError, TypeError):
                    continue

        if version_entries:
            db.session.bulk_save_objects(version_entries)
            db.session.commit()
            version_count = len(version_entries)
        else:
            version_count = len(version_items)
        version_entries = []

        # Batch insert DLCs
        dlc_entries = []
        seen_dlcs = set()  # (base, dlc)

        cnmts_items = list((_cnmts_db or {}).items())
        for i, (base_tid, dlcs) in enumerate(cnmts_items):
            if gevent and i % 50 == 0:
                gevent.sleep(0.001)

            base_upper = base_tid.upper()
            for dlc_app_id in dlcs.keys():
                dlc_upper = dlc_app_id.upper()
                if (base_upper, dlc_upper) in seen_dlcs:
                    continue
                seen_dlcs.add((base_upper, dlc_upper))

                dlc_entries.append(TitleDBDLCs(base_title_id=base_upper, dlc_app_id=dlc_upper))

                if len(dlc_entries) >= BATCH_SIZE * 2:
                    db.session.bulk_save_objects(dlc_entries)
                    db.session.commit()
                    dlc_entries = []
                    if gevent:
                        gevent.sleep(0.01)

        if dlc_entries:
            db.session.bulk_save_objects(dlc_entries)
            db.session.commit()
            dlc_count = len(dlc_entries)
        else:
            dlc_count = len(seen_dlcs)
        dlc_entries = []

        _titledb_cache_timestamp = time.time()  # Use time.time() for cache TTL comparison
        logger.info(f"TitleDB saved to DB cache: {title_count} titles, {version_count} versions, {dlc_count} DLCs")
        return True

    except Exception as e:
        logger.error(f"Error saving TitleDB to cache: {e}")
        try:
            db.session.rollback()
        except:
            pass
        return False


def is_db_cache_valid():
    """Check if database cache is still valid (not expired)."""
    global _titledb_cache_timestamp, _titledb_cache_ttl

    if _titledb_cache_timestamp is None:
        return False

    age = time.time() - _titledb_cache_timestamp
    return age < _titledb_cache_ttl


def get_titledb_cache_timestamp():
    """Get the timestamp of the latest TitleDB cache update."""
    global _titledb_cache_timestamp
    return _titledb_cache_timestamp


def set_titledb_cache_timestamp(timestamp):
    """Set the TitleDB cache timestamp (used after loading from files)."""
    global _titledb_cache_timestamp
    _titledb_cache_timestamp = timestamp


def robust_json_load(filepath):
    """Reliably load JSON files even with invalid escape sequences or control characters."""
    if not os.path.exists(filepath):
        return None

    # Try 0: Fast load first (Native JSON parser is much faster)
    try:
        filesize = os.path.getsize(filepath)
        if filesize < 200 * 1024 * 1024:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                return json.load(f)
    except Exception as e:
        # Step 1: Semi-Fast Load - Fix invalid escapes with Regex
        # This is the most common issue in TitleDB JSONs (bare backslashes)
        logger.warning(f"Fast JSON load failed for {os.path.basename(filepath)}: {e}. Attempting regex sanitization...")
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            # Pattern to match a valid escape sequence OR a bare backslash
            # Group 1 captures valid escapes, Group 3 captures bare backslashes
            import re
            pattern = re.compile(r"(\\([\"\\/bfnrt]|u[0-9a-fA-F]{4}))|(\\)")
            
            def replace_func(m):
                return m.group(1) if m.group(1) else r"\\"
            
            # Correct only bare backslashes
            content = pattern.sub(replace_func, content)
            
            # Try loading again with strict=False
            return json.loads(content, strict=False)
        except Exception as e2:
            logger.warning(f"Regex sanitization failed: {e2}. Falling back to slow robust recovery...")

    # Step 2: Stream Recovery for Large Files (>10MB) - Fallback for heavily corrupted files
    try:
        filesize = os.path.getsize(filepath)
        if filesize > 10 * 1024 * 1024:
            logger.info(f"File {filepath} is large ({filesize / 1024 / 1024:.2f} MB). Attempting stream recovery...")

            try:
                from large_json_sanitizer import sanitize_large_json_file
                sanitized = sanitize_large_json_file(filepath)

                if sanitized and len(sanitized) > 0:
                    logger.info(f"Stream recovery successful! Recovered {len(sanitized)} entries.")
                    return sanitized
            except Exception as e:
                logger.error(f"Error in stream recovery: {e}")
    except Exception:
        pass

    return None

    return None


def getDirsAndFiles(path):
    entries = os.listdir(path)
    allFiles = []
    allDirs = []

    for entry in entries:
        if entry.startswith("._"):
            continue
        fullPath = os.path.join(path, entry)
        if os.path.isdir(fullPath):
            allDirs.append(fullPath)
            dirs, files = getDirsAndFiles(fullPath)
            allDirs += dirs
            allFiles += files
        elif "." + fullPath.split(".")[-1].lower() in ALLOWED_EXTENSIONS:
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
        title_id = base_id + "000"
    elif app_type == APP_TYPE_DLC:
        title_id = hex(int(base_id, base=16) - 1)[2:].rjust(len(base_id), "0") + "000"
    return title_id.upper()


def get_file_size(filepath):
    return os.path.getsize(filepath)


def get_file_info(filepath):
    filedir, filename = os.path.split(filepath)
    extension = filename.split(".")[-1]

    compressed = False
    if extension in ["nsz", "xcz"]:
        compressed = True

    return {
        "filepath": filepath,
        "filedir": filedir,
        "filename": filename,
        "extension": extension,
        "compressed": compressed,
        "size": get_file_size(filepath),
    }


def identify_appId(app_id):
    app_id = app_id.lower()

    global _cnmts_db, _dlc_map
    if _cnmts_db is None:
        logger.error("cnmts_db is not loaded. Call load_titledb first.")
        return None, None

    # Strategy 1: Direct lookup in cnmts_db (usually keyed by Base Title ID)
    if app_id in _cnmts_db:
        app_id_keys = list(_cnmts_db[app_id].keys())
        if len(app_id_keys):
            app = _cnmts_db[app_id][app_id_keys[-1]]

            if app["titleType"] == 128:
                app_type = APP_TYPE_BASE
                title_id = app_id.upper()
            elif app["titleType"] == 129:
                app_type = APP_TYPE_UPD
                if "otherApplicationId" in app and app["otherApplicationId"]:
                    title_id = app["otherApplicationId"].upper()
                else:
                    title_id = get_title_id_from_app_id(app_id, app_type)
            elif app["titleType"] == 130:
                app_type = APP_TYPE_DLC
                if "otherApplicationId" in app and app["otherApplicationId"]:
                    title_id = app["otherApplicationId"].upper()
                else:
                    title_id = get_title_id_from_app_id(app_id, app_type)
        else:
            logger.warning(f"{app_id} has no keys in cnmts_db, fallback to default identification.")
            if app_id.endswith("000"):
                app_type = APP_TYPE_BASE
                title_id = app_id
            elif app_id.endswith("800"):
                app_type = APP_TYPE_UPD
                title_id = get_title_id_from_app_id(app_id, app_type)
            else:
                app_type = APP_TYPE_DLC
                title_id = get_title_id_from_app_id(app_id, app_type)

    # Strategy 2: Reverse DLC Map lookup (if we are dealing with a DLC ID)
    elif _dlc_map and app_id.upper() in _dlc_map:
        base_id = _dlc_map[app_id.upper()]
        title_id = base_id.upper()
        app_type = APP_TYPE_DLC
        # logger.debug(f"Identified DLC {app_id} -> Base {title_id} using reverse map")

    # Strategy 3: Fallback heuristic
    else:
        logger.warning(f"{app_id} not in cnmts_db, fallback to default identification.")
        if app_id.endswith("000"):
            app_type = APP_TYPE_BASE
            title_id = app_id
        elif app_id.endswith("800"):
            app_type = APP_TYPE_UPD
            title_id = get_title_id_from_app_id(app_id, app_type)
        else:
            app_type = APP_TYPE_DLC
            title_id = get_title_id_from_app_id(app_id, app_type)

    return title_id.upper() if title_id else app_id.upper(), app_type


def load_titledb(force=False):
    global _cnmts_db
    global _titles_db
    global _versions_db
    global _versions_txt_db
    global identification_in_progress_count
    global _titles_db_loaded
    global _titledb_cache_timestamp
    global _titledb_cache_ttl

    identification_in_progress_count += 1

    # Verificar se o cache expirou (TTL)
    current_time = time.time()
    cache_expired = False
    if _titledb_cache_timestamp is not None:
        # Obter TTL das configurações se disponível
        try:
            app_settings = load_settings()
            _titledb_cache_ttl = app_settings.get("titledb", {}).get("cache_ttl", 3600)
        except:
            pass  # Usar padrão se não conseguir carregar settings

        elapsed = current_time - _titledb_cache_timestamp
        if elapsed > _titledb_cache_ttl:
            cache_expired = True
            logger.info(f"TitleDB cache expired (TTL: {_titledb_cache_ttl}s, elapsed: {elapsed:.0f}s). Reloading...")

    if force or cache_expired:
        _titles_db_loaded = False
        _titledb_cache_timestamp = None

    if not _titles_db_loaded:
        # Priority 1: Try loading from database cache (fast - < 100ms)
        if is_db_cache_valid():
            if load_titledb_from_db():
                identification_in_progress_count -= 1
                return

        logger.info("Loading TitleDBs into memory...")

        # Ensure TitleDB directory exists
        try:
            os.makedirs(TITLEDB_DIR, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create TitleDB directory: {e}")

        # Diagnostic: List files in TitleDB dir
        try:
            files = os.listdir(TITLEDB_DIR)
            logger.info(f"Files in TitleDB directory: {', '.join(files)}")
        except Exception as e:
            logger.warning(f"Could not list TitleDB directory: {e}")

        app_settings = load_settings()

        _cnmts_db = robust_json_load(os.path.join(TITLEDB_DIR, "cnmts.json"))

        # Database fallback chain: Region -> US/en -> Generic titles.json
        region = app_settings.get("titles", {}).get("region", "US")
        language = app_settings.get("titles", {}).get("language", "en")
        
        # 1. Base files that provide structural data
        load_order = ["titles.json"]
        
        # 2. Heuristic to pick the BEST regional file (most specific first)
        possible_regional = titledb.get_region_titles_filenames(region, language)
        
        # Fallback to US English if not in US
        if region != "US":
             possible_regional += ["titles.US.en.json", "US.en.json"]
        
        # Add the first one that actually exists to the load order
        regional_file_found = None
        for f in possible_regional:
            if os.path.exists(os.path.join(TITLEDB_DIR, f)):
                if f not in load_order:
                    load_order.append(f)
                    regional_file_found = f
                    break # Only load the most specific regional file
        
        # 3. Always load custom.json last for manual overrides
        load_order.append("custom.json")
        
        _titles_db = {}
        global _loaded_titles_file
        _loaded_titles_file = []  # Track files actually successfully loaded

        logger.info(f"TitleDB Load Order: {', '.join(load_order)}")

        for filename in load_order:
            filepath = os.path.join(TITLEDB_DIR, filename)
            # Skip corrupted files
            if filename.endswith(".corrupted") or filepath.endswith(".corrupted"):
                continue
                
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                logger.info(f"Loading TitleDB: {filename}...")
                loaded = robust_json_load(filepath)
                if loaded:
                    count = len(loaded) if isinstance(loaded, (dict, list)) else 0
                    if count > 0:
                        is_custom = filename == "custom.json"
                        # Convert list to dict if necessary for merging
                        current_batch = {}
                        if isinstance(loaded, list):
                            for item in loaded:
                                if isinstance(item, dict) and "id" in item and item["id"]:
                                    current_batch[item["id"].upper()] = item
                        else:
                            current_batch = {k.upper(): v for k, v in loaded.items() if isinstance(v, dict) and k}
                        
                        # MERGE logic: Overwrite names/descriptions but keep existing metadata
                        # Optimization: Yield every 2000 items to prevent worker timeout
                        if not _titles_db:
                            _titles_db = current_batch
                        else:
                            i = 0
                            for tid, data in current_batch.items():
                                i += 1
                                if i % 1000 == 0:
                                    try:
                                        import gevent
                                        gevent.sleep(0.001)
                                    except:
                                        pass
                                        
                                if tid in _titles_db:
                                    if is_custom:
                                        _titles_db[tid].update(data)
                                    else:
                                        # Only override specific human-readable fields
                                        for field in ["name", "description", "publisher", "releaseDate", "category", "genre"]:
                                            val = data.get(field)
                                            if val is not None and val != "":
                                                _titles_db[tid][field] = val
                                else:
                                    _titles_db[tid] = data
                        
                        _loaded_titles_file.append(filename)
                        logger.info(f"SUCCESS: Merged {count} items from {filename} {'(AS OVERRIDE)' if is_custom else ''}")
                else:
                    logger.warning(f"Could not parse {filename}, skipping...")


        if _titles_db:
            # Our _titles_db is already keyed by TitleID (upper) due to the merge logic above.
            # We just need to ensure everything is indexed correctly.
            logger.info(f"TitleDB loaded and indexed: {len(_titles_db)} unique titles.")

        if not _titles_db:
            logger.error("CRITICAL: Failed to load any TitleDB. Game identification will be limited.")
            _titles_db = {}

        _versions_db_path = os.path.join(TITLEDB_DIR, "versions.json")
        # Skip corrupted versions.json
        if os.path.exists(_versions_db_path) and not _versions_db_path.endswith(".corrupted"):
            _versions_db = robust_json_load(_versions_db_path) or {}
        else:
            _versions_db = {}
        _cnmts_db = _cnmts_db or {}

        _titles_db_loaded = True
        _titledb_cache_timestamp = time.time()  # Use Unix timestamp for consistency
        logger.info(f"TitleDBs loaded. Cache TTL: {_titledb_cache_ttl}s")

        # Save to database cache for fast loading next time
        source_files = {}
        for f in _loaded_titles_file:
            source_files[f.lower().replace(".json", "")] = f
        save_titledb_to_db(source_files)

        # Sync metadata to database if loaded
        if _titles_db:
            try:
                sync_titles_to_db()
            except Exception as e:
                logger.error(f"Failed to sync TitleDB to database: {e}")


@debounce(30)
def unload_titledb():
    global _cnmts_db
    global _titles_db
    global _versions_db
    global _versions_txt_db
    global identification_in_progress_count
    global _titles_db_loaded
    global _titledb_cache_timestamp

    if identification_in_progress_count:
        logger.debug("Identification still in progress, not unloading TitleDB.")
        return

    logger.info("Unloading TitleDBs from memory...")
    _cnmts_db = None
    _titles_db = None
    _versions_db = None
    _titles_db_loaded = False
    _titledb_cache_timestamp = None  # Limpar timestamp do cache
    logger.info("TitleDBs unloaded.")


def identify_file_from_filename(filename):
    title_id = None
    app_id = None
    app_type = None
    version = None
    errors = []

    app_id = get_app_id_from_filename(filename)
    if app_id is None:
        errors.append(
            "Could not determine App ID from filename, pattern [APPID] not found. Title ID and Type cannot be derived."
        )
    else:
        title_id, app_type = identify_appId(app_id)

    version = get_version_from_filename(filename)
    if version is None:
        errors.append("Could not determine version from filename, pattern [vVERSION] not found.")

    error = " ".join(errors)
    return app_id, title_id, app_type, version, error


def identify_file_from_cnmt(filepath):
    contents = []
    titleId = None
    version = None
    titleType = None
    container = factory(Path(filepath).resolve())
    container.open(filepath, "rb")
    if filepath.lower().endswith((".xci", ".xcz")):
        container = container.hfs0["secure"]
    try:
        for nspf in container:
            if isinstance(nspf, Nca.Nca) and nspf.header.contentType == Type.Content.META:
                for section in nspf:
                    if isinstance(section, Pfs0.Pfs0):
                        Cnmt = section.getCnmt()

                        titleType = FsTools.parse_cnmt_type_n(
                            hx(
                                Cnmt.titleType.to_bytes(
                                    length=(min(Cnmt.titleType.bit_length(), 1) + 7) // 8, byteorder="big"
                                )
                            )
                        )
                        if titleType == "GAME":
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
    error = ""
    if Keys.keys_loaded:
        identification = "cnmt"
        try:
            cnmt_contents = identify_file_from_cnmt(filepath)
            if not cnmt_contents:
                error = "No content found in NCA containers."
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
            logger.error(f"Could not identify file {filepath} from metadata: {e}")
            error = str(e)
            success = False

    else:
        identification = "filename"
        app_id, title_id, app_type, version, error = identify_file_from_filename(filename)
        if not error:
            contents.append((title_id, app_type, app_id, version))
        else:
            success = False

    if contents:
        contents = [
            {
                "title_id": c[0],
                "app_id": c[2],
                "type": c[1],
                "version": c[3],
            }
            for c in contents
        ]

    # IMPORTANT: Even if keys failed, we still want to return a result
    # if filename identification worked
    if not contents and not success:
        # Fallback to filename identification if CNMT failed
        app_id, title_id, app_type, version, error = identify_file_from_filename(filename)
        if title_id:
            contents = [
                {
                    "title_id": title_id,
                    "app_id": app_id,
                    "type": app_type,
                    "version": version,
                }
            ]
            identification = "filename"
            success = True  # Consider it a success if we got something from filename

    return identification, success, contents, error


def get_game_info(title_id):
    from db import Titles

    global _titles_db

    if title_id is None:
        logger.error("get_game_info called with title_id=None")
        return None

    search_id = str(title_id).upper()

    # 1. Try to get from database first (including custom edits)
    try:
        db_title = Titles.query.filter_by(title_id=search_id).first()
        if db_title and (db_title.name or db_title.is_custom):
            # Get screenshots from TitleDB
            screenshots = []
            if not _titles_db:
                load_titledb()
            if _titles_db:
                info = _titles_db.get(search_id)
                if info:
                    screenshots = info.get("screenshots", []) or []

            # If we have basic info or it's custom, return it
            return {
                "name": db_title.name or "Unknown Title",
                "bannerUrl": db_title.banner_url or "",
                "iconUrl": db_title.icon_url or "",
                "id": db_title.title_id,
                "category": db_title.category.split(",") if db_title.category else [],
                "release_date": format_release_date(db_title.release_date),
                "size": db_title.size or 0,
                "publisher": db_title.publisher or "Nintendo",
                "description": db_title.description or "",
                "nsuid": db_title.nsuid or "",
                "is_custom": db_title.is_custom,
                "screenshots": screenshots,
            }
    except Exception as e:
        logger.error(f"Error querying database for game info {search_id}: {e}")

    # 2. Fallback to Memory/JSON TitleDB
    if not _titles_db:
        load_titledb()

    if not _titles_db:
        return {
            "name": f"Unknown ({title_id})",
            "bannerUrl": "",
            "iconUrl": "",
            "id": title_id,
            "category": [],
            "release_date": "",
            "size": 0,
            "publisher": "--",
            "description": "Database not loaded. Please update TitleDB in settings.",
        }

    try:
        info = _titles_db.get(search_id)
        if not info:
            # Case-insensitive fallback
            info = _titles_db.get(search_id.upper()) or _titles_db.get(search_id.lower())

        if info:
            res = {
                "name": info.get("name") or "Unknown Title",
                "bannerUrl": info.get("bannerUrl") or info.get("banner_url") or "",
                "iconUrl": info.get("iconUrl") or info.get("icon_url") or "",
                "id": info.get("id") or title_id,
                "category": info.get("category", [])
                if isinstance(info.get("category"), list)
                else [info.get("category")]
                if info.get("category")
                else [],
                "release_date": format_release_date(info.get("releaseDate") or info.get("release_date")),
                "size": info.get("size") or 0,
                "publisher": info.get("publisher") or "Nintendo",
                "description": info.get("description") or "",
                "nsuid": info.get("nsuid") or info.get("nsuId") or "",
                "screenshots": info.get("screenshots", []),
            }

            # DLC/Update Icon Fallback: Only if icon is strictly missing
            if not res["iconUrl"] and not search_id.endswith("000"):
                possible_base_ids = [search_id[:-3] + "000"]
                try:
                    # For DLCs, the base ID is often (DLC_PREFIX - 1) + 000
                    prefix = search_id[:-3]
                    base_prefix = hex(int(prefix, 16) - 1)[2:].upper().rjust(13, "0")
                    possible_base_ids.append(base_prefix + "000")
                except:
                    pass

                for bid in possible_base_ids:
                    # Avoid infinite recursion
                    if bid == search_id:
                        continue
                    base_info = get_game_info(bid)
                    if base_info and base_info.get("iconUrl") and not base_info["name"].startswith("Unknown"):
                        res["iconUrl"] = base_info["iconUrl"]
                        res["bannerUrl"] = res["bannerUrl"] or base_info.get("bannerUrl")
                        logger.debug(f"Inherited visuals from base game {bid} for {search_id}")
                        break

            # Fallback: Use Banner as Icon if Icon is still missing
            if not res["iconUrl"] and res["bannerUrl"]:
                res["iconUrl"] = res["bannerUrl"]

            return res

        # If not found, try to find parent BASE game if this is a DLC/UPD
        if not search_id.endswith("000"):
            possible_base_ids = [search_id[:-3] + "000"]
            try:
                prefix = search_id[:-3]
                base_prefix = hex(int(prefix, 16) - 1)[2:].upper().rjust(13, "0")
                possible_base_ids.append(base_prefix + "000")
            except:
                pass

            for bid in possible_base_ids:
                logger.debug(f"ID {search_id} not found, attempting fallback to base {bid}")
                base_info = get_game_info(bid)
                if base_info and not base_info["name"].startswith("Unknown"):
                    return {
                        "name": f"{base_info['name']} [DLC/UPD]",
                        "bannerUrl": base_info["bannerUrl"],
                        "iconUrl": base_info["iconUrl"],
                        "id": title_id,
                        "category": base_info["category"],
                        "release_date": base_info["release_date"],
                        "size": 0,
                        "publisher": base_info["publisher"],
                        "description": f"Informação estendida do jogo base: {base_info['name']}",
                        "nsuid": base_info.get("nsuid", ""),
                    }

        raise Exception(f"ID {search_id} not found in database")
    except Exception as e:
        logger.debug(f"Identification failed for {title_id}: {e}")
        safe_id = str(title_id).upper() if title_id else "UNKNOWN"
        return {
            "name": f"Unknown ({title_id})",
            "bannerUrl": "",
            "iconUrl": "",
            "id": safe_id,
            "category": [],
            "release_date": "",
            "size": 0,
            "publisher": "--",
            "description": "ID não encontrado no banco de dados. Por favor, atualize o TitleDB nas configurações.",
            "nsuid": "",
        }


def get_update_number(version):
    return int(version) // 65536


def get_game_latest_version(all_existing_versions):
    return max(v["version"] for v in all_existing_versions)


def get_all_existing_versions(titleid):
    global _versions_db

    if _versions_db is None:
        logger.warning("versions_db is not loaded. Call load_titledb first.")
        return []

    if not titleid:
        return []

    titleid = titleid.lower()
    versions_dict = {}  # Key: version_int, Value: release_date

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
            "version": v,
            "update_number": get_update_number(v),
            "release_date": rd,
        }
        for v, rd in sorted(versions_dict.items())
    ]

    return []


def get_all_app_existing_versions(app_id):
    global _cnmts_db
    if _cnmts_db is None:
        logger.warning("cnmts_db is not loaded. Call load_titledb first.")
        return None

    app_id = app_id.lower()
    if app_id in _cnmts_db:
        versions_from_cnmts_db = _cnmts_db[app_id].keys()
        if len(versions_from_cnmts_db):
            return sorted(versions_from_cnmts_db)
        else:
            logger.warning(f"No keys in cnmts.json for app ID: {app_id.upper()}")
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


def get_all_existing_dlc(title_id):
    global _cnmts_db
    if _cnmts_db is None:
        logger.error("cnmts_db is not loaded. Call load_titledb first.")
        return []

    title_id = title_id.lower()
    dlcs = []
    for app_id in _cnmts_db.keys():
        # Ensure we iterate over versions (0, 65536, etc)
        app_versions = _cnmts_db[app_id]
        if isinstance(app_versions, dict):
            for version_key, version_description in app_versions.items():
                if (
                    version_description.get("titleType") == 130
                    and version_description.get("otherApplicationId") == title_id
                ):
                    if app_id.upper() not in dlcs:
                        dlcs.append(app_id.upper())
    return dlcs


def get_loaded_titles_file():
    """Return the currently loaded titles filename(s)"""
    global _loaded_titles_file
    if isinstance(_loaded_titles_file, list):
        # Prefer showing the most specific/regional file if multiple were merged
        for f in reversed(_loaded_titles_file):
            if "." in f and any(ext in f.lower() for ext in [".br", "pt", "pt.json", "br.json"]):
                return f
        return _loaded_titles_file[-1] if _loaded_titles_file else "None"
    return _loaded_titles_file or "None"


def get_custom_title_info(title_id):
    """Retrieve custom info for a specific TitleID from custom.json"""
    custom_path = os.path.join(TITLEDB_DIR, "custom.json")
    custom_db = robust_json_load(custom_path) or {}
    return custom_db.get(title_id.upper())


def search_titledb_by_name(query):
    """Search for games in the loaded TitleDB by name."""
    global _titles_db
    if not _titles_db:
        return []

    results = []
    query = query.lower()

    # Simple iteration - could be optimized with an index if needed but for <20k items it's fine
    for tid, data in _titles_db.items():
        name = data.get("name", "")
        if name and query in name.lower():
            results.append(
                {
                    "id": tid,
                    "name": name,
                    "region": data.get("region", "--"),
                    "iconUrl": data.get("iconUrl"),
                    "bannerUrl": data.get("bannerUrl"),
                    "publisher": data.get("publisher"),
                    "description": data.get("description"),
                }
            )
            if len(results) >= 50:
                break

    return results


def save_custom_title_info(title_id, data):
    """
    Save custom info for a TitleID to database and custom.json.
    data should contain: name, description, publisher, iconUrl, bannerUrl, ...
    """
    from db import db, Titles

    global _titles_db

    if not title_id or not data:
        return False, "Missing TitleID or Data"

    title_id = title_id.upper()

    # 1. Update Database
    try:
        db_title = Titles.query.filter_by(title_id=title_id).first()
        if not db_title:
            db_title = Titles(title_id=title_id)
            db.session.add(db_title)

        db_title.name = data.get("name", db_title.name)
        db_title.description = data.get("description", db_title.description)
        db_title.publisher = data.get("publisher", db_title.publisher)
        db_title.icon_url = data.get("iconUrl", db_title.icon_url)
        db_title.banner_url = data.get("bannerUrl", db_title.banner_url)
        db_title.category = (
            ",".join(data.get("category"))
            if isinstance(data.get("category"), list)
            else data.get("category", db_title.category)
        )
        db_title.release_date = data.get("releaseDate", data.get("release_date", db_title.release_date))
        db_title.size = data.get("size", db_title.size)
        db_title.nsuid = data.get("nsuid", db_title.nsuid)
        db_title.is_custom = True

        db.session.commit()
        logger.info(f"Saved custom info to database for {title_id}")
    except Exception as e:
        logger.error(f"Error saving custom info to DB for {title_id}: {e}")
        db.session.rollback()

    # 2. Legacy Support: Update custom.json
    custom_path = os.path.join(TITLEDB_DIR, "custom.json")
    os.makedirs(os.path.dirname(custom_path), exist_ok=True)
    custom_db = robust_json_load(custom_path) or {}

    # Map fields for compatibility with TitleDB format
    save_data = data.copy()
    if "genre" in save_data:
        save_data["category"] = save_data.pop("genre")
    if "release_date" in save_data:
        save_data["releaseDate"] = save_data.pop("release_date")
    save_data["id"] = title_id

    if title_id in custom_db and isinstance(custom_db[title_id], dict):
        custom_db[title_id].update(save_data)
    else:
        custom_db[title_id] = save_data

    try:
        safe_write_json(custom_path, custom_db, indent=4)

        # 3. Update in-memory DB immediately
        if _titles_db is not None:
            if title_id in _titles_db:
                _titles_db[title_id].update(save_data)
            else:
                _titles_db[title_id] = save_data

        return True, None
    except Exception as e:
        logger.error(f"Error saving custom.json: {e}")
        return False, str(e)


def sync_titles_to_db(force=False):
    """
    Sync metadata from _titles_db (loaded from JSON) to Database Titles table.
    Only updates titles that are NOT marked as 'is_custom'.
    """
    from db import db, Titles

    global _titles_db

    if not _titles_db:
        logger.warning("sync_titles_to_db: TitleDB not loaded, skipping sync.")
        return

    from flask import has_app_context

    if not has_app_context():
        logger.warning("sync_titles_to_db: No app context, skipping sync.")
        return

    logger.info("Syncing TitleDB metadata to database...")

    try:
        # Get all titles currently in DB to avoid bulk queries in loop
        # We only sync titles that exist in our database (library/wishlist/identified)
        # to avoid bloat. If a game is new, it will be added when identified.
        try:
            db_titles = Titles.query.all()
        except Exception as e:
            if "no such column" in str(e).lower():
                logger.warning(
                    "sync_titles_to_db: Database schema is outdated (missing columns). Skipping sync until next restart."
                )
                return
            raise e

        db_titles_map = {t.title_id.upper(): t for t in db_titles if t.title_id}

        updated_count = 0
        # Optimization: Only iterate over titles that are actually in our DB
        # instead of iterating over all 24k+ titles from the JSON
        for tid, title in db_titles_map.items():
            if tid in _titles_db:
                tdb_info = _titles_db[tid]
                
                # Only update if NOT custom
                if not title.is_custom:
                    title.name = tdb_info.get("name", title.name)
                    title.description = tdb_info.get("description", title.description)
                    title.publisher = tdb_info.get("publisher", title.publisher)
                    title.icon_url = tdb_info.get("iconUrl", title.icon_url)
                    title.banner_url = tdb_info.get("bannerUrl", title.banner_url)

                    cat = tdb_info.get("category", [])
                    title.category = ",".join(cat) if isinstance(cat, list) else cat

                    title.release_date = tdb_info.get("releaseDate", title.release_date)
                    title.size = tdb_info.get("size", title.size)
                    title.nsuid = tdb_info.get("nsuid", title.nsuid)
                    updated_count += 1
                
                # Periodic yield for safety
                if updated_count % 500 == 0:
                    yield_to_event_loop()

        db.session.commit()
        logger.info(f"Sync complete. Updated {updated_count} titles in database metadata tracker.")
    except Exception as e:
        logger.error(f"Error during TitleDB-to-DB sync: {e}")
        db.session.rollback()
