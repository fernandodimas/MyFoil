import os
import re
import json
import time
import fcntl
import sqlite3

try:
    import gevent
except ImportError:
    gevent = None

import titledb
# import titledb_cache_file  # REMOVED: File cache deprecated
print("DEBUG: titles.py imported", flush=True)
from constants import APP_TYPE_BASE, APP_TYPE_UPD, APP_TYPE_DLC, TITLEDB_DIR, TITLEDB_DEFAULT_FILES, ALLOWED_EXTENSIONS, CONFIG_DIR
from utils import now_utc, ensure_utc, format_size_py, format_datetime, debounce
from settings import load_settings, load_keys
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
            parsed = datetime.strptime(date_str, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return date_str


# Global variables for TitleDB data
identification_in_progress_count = 0
_titles_db_loaded = False


def yield_to_event_loop():
    """Yield control to the event loop to prevent blocking"""
    try:
        if gevent:
            gevent.sleep(0.001)
        else:
            time.sleep(0.001)
    except Exception:
        pass  # Ignore sleep errors
_cnmts_db = None
_titles_db = None
_versions_db = None
_dlc_map = {}
_dlcs_by_base_id = {}  # New optimization: {base_id: [dlc_id1, dlc_id2, ...]}
_loaded_titles_file = None  # Track which titles file was loaded
_titledb_cache_timestamp = None  # Timestamp when TitleDB is last loaded
_titledb_cache_ttl = 3600  # TTL in seconds (1 hour default)
_game_info_cache = {}  # In-memory cache for get_game_info results


def get_titles_count():
    global _titles_db
    return len(_titles_db) if _titles_db else 0


# Database cache functions for TitleDB
def load_titledb_from_db():
    """Load TitleDB data from database cache if available and valid."""
    global _titles_db, _versions_db, _cnmts_db, _dlc_map, _dlcs_by_base_id, _titledb_cache_timestamp, _titles_db_loaded

    # Database-only loading logic (Removed File Cache Priority)
    logger.info("Loading TitleDB from PostgreSQL database...")

    # FALLBACK: Load from database
    try:
        from db import TitleDBCache, TitleDBVersions, TitleDBDLCs

        # Check if cache tables exist
        try:
            print("DEBUG: Checking TitleDBCache count...", flush=True)
            cache_count = TitleDBCache.query.count()
            print(f"DEBUG: TitleDBCache count: {cache_count}", flush=True)
            if cache_count == 0:
                logger.info("TitleDB cache is empty, will load from files")
                return False
        except Exception as e:
            print(f"DEBUG: TitleDBCache count failed: {e}", flush=True)
            logger.warning("TitleDB cache tables don't exist yet")
            return False

        # Load titles from cache
        logger.info(f"Loading TitleDB from database cache ({cache_count} titles)...")
        cached_titles = TitleDBCache.query.all()

        _titles_db = {}
        for entry in cached_titles:
            if entry.title_id:
                _titles_db[entry.title_id.upper()] = entry.data

        # Load versions from cache
        cached_versions = TitleDBVersions.query.all()
        _versions_db = {}
        for entry in cached_versions:
            if entry.title_id:
                tid = entry.title_id.lower()
                if tid not in _versions_db:
                    _versions_db[tid] = {}
                _versions_db[tid][str(entry.version)] = entry.release_date

        # Load DLCs from cache and build index + REVERSE MAP
        _cnmts_db = {}
        _dlc_map = {}
        _dlcs_by_base_id = {}
        cached_dlcs = TitleDBDLCs.query.all()
        for entry in cached_dlcs:
            if not entry.base_title_id or not entry.dlc_app_id:
                continue
            base_tid = entry.base_title_id.lower()
            dlc_app_id = entry.dlc_app_id.upper()

            # Build CNMT-style structure for compatibility (Keyed by DLC ID)
            dlc_id_lower = dlc_app_id.lower()
            if dlc_id_lower not in _cnmts_db:
                _cnmts_db[dlc_id_lower] = {}
            _cnmts_db[dlc_id_lower]["0"] = {  # Version dummy
                "titleType": 130,  # DLC type
                "otherApplicationId": base_tid,
            }
            # Populate reverse map
            _dlc_map[dlc_app_id] = base_tid
            
            # Populate optimization index
            if base_tid not in _dlcs_by_base_id:
                _dlcs_by_base_id[base_tid] = []
            if dlc_app_id not in _dlcs_by_base_id[base_tid]:
                _dlcs_by_base_id[base_tid].append(dlc_app_id)

        _titles_db_loaded = True
        _titledb_cache_timestamp = time.time()
        logger.info(
            f"TitleDB loaded from DB cache: {len(_titles_db)} titles, {len(_versions_db)} versions, {len(cached_dlcs)} DLCs"
        )
        return True

    except Exception as e:
        logger.error(f"Error loading TitleDB from cache: {e}")
        return False


def save_titledb_to_db(source_files, app_context=None, progress_callback=None):
    """Save TitleDB data to database cache for fast loading."""
    global _titles_db, _versions_db, _cnmts_db, _titledb_cache_timestamp

    try:
        from flask import has_app_context

        if not has_app_context():
            logger.warning("Cannot save TitleDB cache: no app context")
            return False

        from db import db, TitleDBCache, TitleDBVersions, TitleDBDLCs

        # Use a file lock to prevent concurrent cache saves from different processes (e.g. Workers)
        lock_path = os.path.join(CONFIG_DIR, ".titledb_save.lock")
        lock_file = open(lock_path, "w")
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, IOError):
            logger.info("Outro processo já está salvando o TitleDB no cache. Ignorando esta execução.")
            lock_file.close()
            return True # Not an error, just redundant

        logger.info("Saving TitleDB to database cache...")

        now = now_utc()

        # Optimize SQLite for bulk operations
        import time
        from sqlalchemy.exc import OperationalError
        
        is_sqlite = "sqlite" in str(db.engine.url)
        
        if is_sqlite:
            logger.info("Applying SQLite optimizations for bulk insert...")
            try:
                # Increase cache size to 64MB for faster operations
                db.session.execute(db.text("PRAGMA cache_size = -64000"))
                # Store temp tables in memory
                db.session.execute(db.text("PRAGMA temp_store = MEMORY"))
                # Use synchronous=OFF during bulk insert (faster, slight risk if crash mid-operation)
                db.session.execute(db.text("PRAGMA synchronous = OFF"))
                db.session.commit()
                logger.info("✅ SQLite optimizations applied")
            except Exception as e:
                logger.warning(f"Could not apply all optimizations: {e}")
                db.session.rollback()
        
        # Note: We skip DELETE and rely on INSERT OR REPLACE (upsert pattern)
        # This is MUCH faster as it avoids exclusive table lock from DELETE
        logger.info(f"Using UPSERT pattern ({'INSERT OR REPLACE' if is_sqlite else 'ON CONFLICT'})")
        
        max_retries = 3
        retry_delay = 2


        # Try to import gevent for cooperative multitasking
        try:
            import gevent
        except ImportError:
            gevent = None

        # Deduplicate titles just in case (though dict keys should be unique)
        seen_titles = set()
        pending_entries = []
        BATCH_SIZE = 500  # Reduced from 2000 to minimize SQLite lock duration

        logger.info(f"Starting to process {len(_titles_db)} titles in batches of {BATCH_SIZE}...")
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
                for attempt in range(max_retries):
                    try:
                        # Convert objects to dicts for bulk save
                        mappings = [
                            {
                                "title_id": e.title_id,
                                "data": json.dumps(e.data),
                                "source": e.source,
                                "downloaded_at": e.downloaded_at,
                                "updated_at": e.updated_at,
                            }
                            for e in pending_entries
                        ]
                        
                        if is_sqlite:
                            sql = """
                                INSERT OR REPLACE INTO titledb_cache (title_id, data, source, downloaded_at, updated_at)
                                VALUES (:title_id, :data, :source, :downloaded_at, :updated_at)
                            """
                        else:
                            # PostgreSQL UPSERT syntax
                            sql = """
                                INSERT INTO titledb_cache (title_id, data, source, downloaded_at, updated_at)
                                VALUES (:title_id, :data, :source, :downloaded_at, :updated_at)
                                ON CONFLICT (title_id) DO UPDATE SET
                                data = EXCLUDED.data,
                                source = EXCLUDED.source,
                                downloaded_at = EXCLUDED.downloaded_at,
                                updated_at = EXCLUDED.updated_at
                            """

                        db.session.execute(db.text(sql), mappings)
                        db.session.commit()
                        break
                    except OperationalError as e:
                        if "locked" in str(e).lower() and attempt < max_retries - 1:
                            wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                            logger.warning(f"DB locked during bulk save (attempt {attempt+1}/{max_retries}). Retrying in {wait_time}s...")
                            db.session.rollback()
                            time.sleep(wait_time)
                            continue
                        raise
                    except Exception as e:
                        logger.error(f"Error during bulk save: {e}")
                        db.session.rollback()
                        raise
                pending_entries = []  # Release memory
                
                # Progress update if possible
                if progress_callback:
                    prog = 81 + int((i / len(_titles_db)) * 10)
                    progress_callback(f"Salvando títulos no cache ({i}/{len(_titles_db)})...", prog)

                # Yield after DB commit
                if gevent:
                    gevent.sleep(0.01)

        # Save remaining entries
        title_count = len(seen_titles)
        if pending_entries:
            for attempt in range(max_retries):
                try:
                    mappings = [
                        {
                                "title_id": e.title_id,
                                "data": json.dumps(e.data),
                                "source": e.source,
                                "downloaded_at": e.downloaded_at,
                                "updated_at": e.updated_at,
                        }
                        for e in pending_entries
                    ]
                    if is_sqlite:
                        sql = """
                            INSERT OR REPLACE INTO titledb_cache (title_id, data, source, downloaded_at, updated_at)
                            VALUES (:title_id, :data, :source, :downloaded_at, :updated_at)
                        """
                    else:
                        # PostgreSQL UPSERT syntax
                        sql = """
                            INSERT INTO titledb_cache (title_id, data, source, downloaded_at, updated_at)
                            VALUES (:title_id, :data, :source, :downloaded_at, :updated_at)
                            ON CONFLICT (title_id) DO UPDATE SET
                            data = EXCLUDED.data,
                            source = EXCLUDED.source,
                            downloaded_at = EXCLUDED.downloaded_at,
                            updated_at = EXCLUDED.updated_at
                        """
                    
                    db.session.execute(db.text(sql), mappings)
                    db.session.commit()
                    break
                except OperationalError as e:
                    if "locked" in str(e).lower() and attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(f"DB locked during final bulk save (attempt {attempt+1}/{max_retries}). Retrying in {wait_time}s...")
                        db.session.rollback()
                        time.sleep(wait_time)
                        continue
                    raise
                except Exception as e:
                    logger.error(f"Error during final bulk save: {e}")
                    db.session.rollback()
                    raise
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

                    if len(version_entries) >= 500:  # Reduced from BATCH_SIZE * 2 to 500 to avoid locks
                        for attempt in range(max_retries):
                            try:
                                db.session.bulk_save_objects(version_entries)
                                db.session.commit()
                                break
                            except OperationalError as e:
                                if "locked" in str(e).lower() and attempt < max_retries - 1:
                                    logger.warning(f"DB locked during versions bulk save (attempt {attempt+1})...")
                                    db.session.rollback()
                                    time.sleep(retry_delay)
                                    continue
                                raise
                        version_entries = []
                        if gevent:
                            gevent.sleep(0.01)
                except (ValueError, TypeError):
                    continue

        if version_entries:
            for attempt in range(max_retries):
                try:
                    db.session.bulk_save_objects(version_entries)
                    db.session.commit()
                    break
                except OperationalError as e:
                    if "locked" in str(e).lower() and attempt < max_retries - 1:
                        logger.warning(f"DB locked during final versions bulk save (attempt {attempt+1})...")
                        db.session.rollback()
                        time.sleep(retry_delay)
                        continue
                    raise
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

                if len(dlc_entries) >= 500:
                    for attempt in range(max_retries):
                        try:
                            db.session.bulk_save_objects(dlc_entries)
                            db.session.commit()
                            break
                        except OperationalError as e:
                            if "locked" in str(e).lower() and attempt < max_retries - 1:
                                logger.warning(f"DB locked during DLC bulk save (attempt {attempt+1})...")
                                db.session.rollback()
                                time.sleep(retry_delay)
                                continue
                            raise
                    dlc_entries = []
                    if gevent:
                        gevent.sleep(0.01)

        # Final batch of DLCs
        if dlc_entries:
            for attempt in range(max_retries):
                try:
                    db.session.bulk_save_objects(dlc_entries)
                    db.session.commit()
                    break
                except OperationalError as e:
                    if "locked" in str(e).lower() and attempt < max_retries - 1:
                        logger.warning(f"DB locked during final DLC bulk save (attempt {attempt+1})...")
                        db.session.rollback()
                        time.sleep(retry_delay)
                        continue
                    raise
            dlc_entries = []

        version_count = len(seen_versions)
        dlc_count = len(seen_dlcs)

        _titledb_cache_timestamp = time.time()  # Use time.time() for cache TTL comparison
        logger.info(f"TitleDB saved to DB cache: {title_count} titles, {version_count} versions, {dlc_count} DLCs")
        
        # ALSO save to file cache for fast loading
        try:
            logger.info("Saving TitleDB to file cache...")
            titledb_cache_file.save_titledb_to_file(_titles_db, _versions_db, _cnmts_db)
        except Exception as file_err:
            logger.warning(f"Could not save to file cache (non-fatal): {file_err}")
        
        return True


    except Exception as e:
        logger.error(f"Error saving TitleDB to cache: {e}")
        try:
            db.session.rollback()
        except Exception as e:
            logger.debug(f"Rollback failed: {e}")
        return False
    finally:
        # Release lock regardless of success or failure
        try:
            if "lock_file" in locals() and not lock_file.closed:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
                lock_file.close()
        except (OSError, ValueError) as e:
            logger.debug(f"Lock cleanup failed: {e}")


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

    # CACHE SYSTEM: Check for pre-sanitized .clean file
    clean_filepath = filepath + ".clean"
    if os.path.exists(clean_filepath):
        # Check if clean file is newer than source file
        if os.path.getmtime(clean_filepath) >= os.path.getmtime(filepath):
            try:
                with open(clean_filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cached clean file {clean_filepath}: {e}")
                # Fall through to process original file
    
    # Try 0: Fast load first (Native JSON parser is much faster)
    try:
        filesize = os.path.getsize(filepath)
        # Increase limit for fast load to avoid unnecessary sanitization for valid big files
        if filesize < 500 * 1024 * 1024: 
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                data = json.load(f)
                
                # Create clean marker for valid files too
                # This prevents re-parsing logic checks next time if we wanted to
                # But mostly we use .clean for files that NEEDED sanitization.
                # However, for consistency, we could just return here.
                return data
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
            data = json.loads(content, strict=False)
            if data:
                # AUTO-REPAIR: Save the sanitized version to .clean file
                # We don't overwrite the original to avoid conflict with downloaders or re-downloads
                logger.info(f"Sanitized {os.path.basename(filepath)} successfully. Saving to cache...")
                try:
                    with open(clean_filepath, 'w', encoding='utf-8') as f:
                        json.dump(data, f)  # Removed indent to save space and I/O time
                    
                    # Update mtime of clean file to be definitely newer than source
                    # (in case everything happened in the same second)
                    now = time.time()
                    times = (now, now)
                    os.utime(clean_filepath, times)
                except Exception as save_err:
                    logger.warning(f"Failed to save auto-repaired JSON: {save_err}")
            return data
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
                    # AUTO-REPAIR: Save the recovered blocks back to disk as a clean JSON
                    logger.info(f"Auto-repairing {os.path.basename(filepath)} with recovered blocks...")
                    try:
                        with open(filepath, 'w', encoding='utf-8') as f:
                            json.dump(sanitized, f)  # Removed indent to save space and I/O time
                    except Exception as save_err:
                        logger.warning(f"Failed to save auto-repaired JSON after stream recovery: {save_err}")
                    return sanitized
            except Exception as e:
                logger.error(f"Error in stream recovery: {e}")
    except Exception:
        pass

    return None

    return None


def getDirsAndFiles(path):
    """
    Find all files with allowed extensions in path recursively.
    Uses os.scandir for better performance and yields to gevent to keep server responsive.
    """
    allFiles = []
    allDirs = []

    try:
        # Avoid blocking the event loop for too long
        if gevent:
            gevent.sleep(0.001) 
        
        with os.scandir(path) as it:
            for i, entry in enumerate(it):
                if gevent and i % 50 == 0:
                    gevent.sleep(0.001)
                
                if entry.name == ".DS_Store":
                    try:
                        os.remove(entry.path)
                        logger.info(f"Deleted .DS_Store: {entry.path}")
                    except OSError:
                        pass
                    continue

                if entry.name.startswith("._"):
                    continue
                
                if entry.is_dir(follow_symlinks=False):
                    fullPath = entry.path
                    allDirs.append(fullPath)
                    dirs, files = getDirsAndFiles(fullPath)
                    allDirs += dirs
                    allFiles += files
                elif entry.is_file():
                    ext = "." + entry.name.split(".")[-1].lower()
                    if ext in ALLOWED_EXTENSIONS:
                        allFiles.append(entry.path)
    except Exception as e:
        logger.error(f"Error scanning directory {path}: {e}")

    return allDirs, allFiles


def get_app_id_from_filename(filename):
    app_id_match = re.search(app_id_regex, filename)
    return app_id_match[1] if app_id_match is not None else None


def get_version_from_filename(filename):
    version_match = re.search(version_regex, filename)
    return version_match[1] if version_match is not None else None


def get_title_id_from_app_id(app_id, app_type):
    """
    Switch IDs use a 16-char hex format.
    Standard: [TitleID 13 hex] [Suffix 3 hex]
    Suffix: 000=Base, 800=Update, 001-7FF=DLC
    
    Heuristic: Most DLCs share the same 13-hex prefix as the Base game.
    However, some publishers use an offset (usually the 13th digit).
    If the 13th digit is ODD, the base game often has that digit as (digit - 1).
    """
    app_id = app_id.upper()
    prefix = app_id[:-3]
    
    # 1. Check Standard Heuristic (Prefix + 000)
    std_id = prefix + "000"
    
    # 2. Check Even/Odd Heuristic (Only if it might be an offset)
    # The 13th character is prefix[-1]
    char_13 = prefix[-1]
    try:
        val = int(char_13, 16)
        # If it's a DLC or UPDATE and the 13th digit is ODD
        if (app_type == APP_TYPE_DLC or app_type == APP_TYPE_UPD) and (val % 2 != 0):
            even_char = hex(val - 1)[2:].upper()
            even_id = prefix[:-1] + even_char + "000"
            
            # If we have TitleDB loaded, we can verify which one is a valid Base Title
            global _titles_db
            if _titles_db:
                # If std_id exists as a BASE title, it's probably the right one
                if std_id.lower() in _titles_db:
                    return std_id
                # If even_id exists but std_id doesn't, even_id is ALMOST CERTAINLY the parent
                if even_id.lower() in _titles_db:
                    return even_id
            
            # Default fallback for odd DLC: the even parent is much more common than a phantom odd parent
            return even_id
    except:
        pass

    return std_id


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
        # Heuristic fallback if DB is not loaded
        if app_id.endswith("000"):
            return app_id.upper(), APP_TYPE_BASE
        elif app_id.endswith("800"):
            return get_title_id_from_app_id(app_id, APP_TYPE_UPD), APP_TYPE_UPD
        else:
            return get_title_id_from_app_id(app_id, APP_TYPE_DLC), APP_TYPE_DLC

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
        logger.debug(f"{app_id} not in cnmts_db, fallback to default identification.")
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


def load_titledb(force=False, progress_callback=None):
    global _titles_db_loaded
    global _titledb_cache_timestamp
    global _titledb_cache_ttl
    global _titles_db
    global _versions_db
    global _cnmts_db
    global _dlc_map
    global _dlcs_by_base_id

    # Verificar se o cache expirou (TTL)
    current_time = time.time()
    cache_expired = False
    if _titledb_cache_timestamp is not None:
        try:
            app_settings = load_settings()
            _titledb_cache_ttl = app_settings.get("titledb", {}).get("cache_ttl", 3600)
        except Exception:
            pass

        elapsed = current_time - _titledb_cache_timestamp
        if elapsed > _titledb_cache_ttl:
            cache_expired = True
            logger.info(f"TitleDB cache expired. Reloading...")

    if force or cache_expired:
        _titles_db_loaded = False
        _titledb_cache_timestamp = None

    if _titles_db_loaded:
        return

    logger.info("Loading TitleDB from database...")
    if progress_callback:
        progress_callback("Carregando banco de dados de títulos...", 10)
    
    if load_titledb_from_db():
        _titles_db_loaded = True
        logger.info(f"TitleDB loaded successfully from DB.")
        # Trigger sync to Database Titles table (metadata tracker)
        try:
            sync_titles_to_db()
        except Exception as sync_err:
            logger.warning(f"Metadata sync after load failed: {sync_err}")
    else:
        logger.warning("Failed to load TitleDB from database (or empty).")
        # Ensure we have empty dicts at least
        if _titles_db is None: _titles_db = {}
        if _versions_db is None: _versions_db = {}
        if _cnmts_db is None: _cnmts_db = {}
        if _dlc_map is None: _dlc_map = {}
        _titles_db_loaded = True # Mark as loaded even if empty to prevent retries loop
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
    global _cnmts_db
    global _titles_db
    global _versions_db
    global _game_info_cache
    _cnmts_db = None
    _titles_db = None
    _versions_db = None
    _titles_db_loaded = False
    _titledb_cache_timestamp = None  # Limpar timestamp do cache
    _game_info_cache = {}  # Clear cache on unload
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
    
    # Debug Logging
    db_size = len(_titles_db) if _titles_db else 0
    logger.info(f"Identifying '{filename}'... (Keys loaded: {Keys.keys_loaded}, TitleDB: {db_size} titles)")
    
    contents = []
    success = True
    error = ""
    if Keys.keys_loaded:
        identification = "cnmt"
        try:
            logger.debug(f"Attempting CNMT identification for {filename}")
            cnmt_contents = identify_file_from_cnmt(filepath)
            if not cnmt_contents:
                logger.debug(f"No CNMT content found for {filename}")
                error = "No content found in NCA containers."
                success = False
            else:
                logger.debug(f"CNMT found for {filename}: {cnmt_contents}")
                for content in cnmt_contents:
                    app_type, app_id, version = content
                    if app_type != APP_TYPE_BASE:
                        # need to get the title ID from cnmts
                        title_id, app_type = identify_appId(app_id)
                    else:
                        title_id = app_id
                    contents.append((title_id, app_type, app_id, version))
        except Exception as e:
            logger.warning(f"Could not identify file {filepath} from metadata (this is common if keys are missing): {e}")
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
        # Check if contents is already a list of dicts (from fallback or newer logic)
        if isinstance(contents[0], dict):
            # Already in dict format, just ensure keys exist
            pass
        else:
            # Convert from tuples (title_id, app_type, app_id, version)
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
        logger.debug(f"Falling back to filename identification for {filename}")
        app_id, title_id, app_type, version, f_error = identify_file_from_filename(filename)
        if title_id:
            logger.debug(f"Filename identification success for {filename}: {title_id}")
            contents = [
                {
                    "title_id": title_id,
                    "app_id": app_id,
                    "type": app_type,
                    "version": version,
                }
            ]
            identification = "filename"
            success = True  
            error = "" # Success in fallback should clear the error

    # Final cleanup of the error string if we found something
    if contents and success:
        error = ""
        
    # Extract suggested name from filename (part before first bracket)
    suggested_name = None
    if contents and success:
        # "Game Name [ID][v0].nsp" -> "Game Name"
        name_part = filename.split('[')[0].strip()
        if name_part and name_part != filename:
            suggested_name = name_part

    return identification, success, contents, error, suggested_name


def get_game_info(title_id, silent=False):
    from db import Titles

    global _titles_db, _game_info_cache

    if title_id is None:
        if not silent:
            logger.error("get_game_info called with title_id=None")
        return None

    search_id = str(title_id).upper()
    
    # 0. Check Cache
    if search_id in _game_info_cache:
        return _game_info_cache[search_id]

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
            res = {
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
            _game_info_cache[search_id] = res
            return res
    except Exception as e:
        if not silent:
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

        # 3. Deep Scan Fallback: If Key lookup failed, search inside values
        # Some JSON sources might key by NSUID or other IDs, but the "id" field usually holds the TitleID
        if not info:
            search_id_upper = search_id.upper()
            for data in _titles_db.values():
                if not isinstance(data, dict):
                    continue
                
                # Check 'id' (TitleID)
                data_id = str(data.get("id", "")).upper()
                if data_id == search_id_upper:
                    info = data
                    break
                
                # Check 'nsuId' (Decimal ID)
                # Only check if search_id looks like decimal? Or just string compare
                data_nsuid = str(data.get("nsuId", "") or data.get("nsuid", ""))
                if data_nsuid == search_id:
                    info = data
                    break

        if info and isinstance(info, dict):
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
                except (ValueError, IndexError):
                    pass  # Invalid hex format

                for bid in possible_base_ids:
                    # Avoid infinite recursion
                    if bid == search_id:
                        continue
                    base_info = get_game_info(bid, silent=True)
                    if base_info and base_info.get("iconUrl") and not base_info["name"].startswith("Unknown"):
                        res["iconUrl"] = base_info["iconUrl"]
                        res["bannerUrl"] = res["bannerUrl"] or base_info.get("bannerUrl")
                        logger.debug(f"Inherited visuals from base game {bid} for {search_id}")
                        break

            # Fallback: Use Banner as Icon if Icon is still missing
            if not res["iconUrl"] and res["bannerUrl"]:
                res["iconUrl"] = res["bannerUrl"]

            # Sanitize name to remove "Nintendo Switch 2 Edition" nonsense if present
            name = res.get("name")
            if name:
                replacements = [
                    " – Nintendo Switch™ 2 Edition",
                    " - Nintendo Switch™ 2 Edition",
                    " – Nintendo Switch 2 Edition",
                    " - Nintendo Switch 2 Edition",
                    " Nintendo Switch 2 Edition",
                ]
                for r in replacements:
                    if r in name:
                        name = name.replace(r, "")
                res["name"] = name.strip()

            _game_info_cache[search_id] = res
            return res

        # If not found, try to find parent BASE game if this is a DLC/UPD
        if not search_id.endswith("000"):
            possible_base_ids = [search_id[:-3] + "000"]
            try:
                prefix = search_id[:-3]
                base_prefix = hex(int(prefix, 16) - 1)[2:].upper().rjust(13, "0")
                possible_base_ids.append(base_prefix + "000")
            except (ValueError, IndexError):
                pass  # Invalid hex format

            for bid in possible_base_ids:
                if not silent:
                    logger.debug(f"ID {search_id} not found, attempting fallback to base {bid}")
                base_info = get_game_info(bid, silent=True)
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
                    _game_info_cache[search_id] = res
                    return res

        raise Exception(f"ID {search_id} not found in database")
    except Exception as e:
        if not silent:
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
        _game_info_cache[search_id] = res
        return res


def get_update_number(version):
    return int(version) // 65536


def get_game_latest_version(all_existing_versions):
    return max(v["version"] for v in all_existing_versions)


def get_all_existing_versions(titleid):
    global _versions_db

    if not _titles_db_loaded:
        load_titledb()

    if _versions_db is None:
        logger.warning("versions_db is not loaded.")
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
            except (ValueError, TypeError):
                continue  # Skip invalid version strings

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

    if not app_id:
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

    if not app_id:
        return None
    app_id = app_id.lower()
    if app_id in _versions_txt_db:
        return _versions_txt_db[app_id]
    return None


def get_all_existing_dlc(title_id):
    global _cnmts_db, _dlcs_by_base_id
    if _cnmts_db is None:
        logger.error("cnmts_db is not loaded. Call load_titledb first.")
        return []

    if not title_id:
        return []
        
    title_id = title_id.lower()
    
    # Priority 1: Use optimization index if available
    if _dlcs_by_base_id and title_id in _dlcs_by_base_id:
        return _dlcs_by_base_id[title_id]

    # Fallback: Sequential scan
    dlcs = []
    for app_id, versions in _cnmts_db.items():
        if isinstance(versions, dict):
            for version_key, version_description in versions.items():
                if (
                    version_description.get("titleType") == 130
                    and version_description.get("otherApplicationId") == title_id
                ):
                    app_id_upper = app_id.upper()
                    if app_id_upper not in dlcs:
                        dlcs.append(app_id_upper)
                    break
    return dlcs


def get_loaded_titles_file():
    """Return the currently loaded titles filename(s) from Database"""
    try:
        from db import TitleDBCache, db
        # Get distinct sources
        with db.session.no_autoflush: 
             # Use distinct to get unique source filenames
             sources = db.session.query(TitleDBCache.source).distinct().all()
        
        source_names = [s[0] for s in sources if s[0]]
        
        if not source_names:
            return "Database (Empty)"
            
        # Filter out common base files to show regional interest
        regional = [s for s in source_names if "titles" not in s and "versions" not in s and "cnmts" not in s and "languages" not in s]
        if regional:
             return ", ".join(sorted(regional))
             
        return ", ".join(sorted(source_names))
    except Exception as e:
        logger.warning(f"Error getting loaded titles file: {e}")
        return "Database (Error)"


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
        if not isinstance(data, dict):
            continue
            
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
                
                if not isinstance(tdb_info, dict):
                    continue
                
                # Only update if NOT custom
                if not title.is_custom:
                    # Simple helper to avoid overwriting with None or empty
                    def set_if_not_empty(obj, attr, val):
                        if val is not None and val != "":
                            setattr(obj, attr, val)

                    set_if_not_empty(title, "name", tdb_info.get("name"))
                    set_if_not_empty(title, "description", tdb_info.get("description"))
                    set_if_not_empty(title, "publisher", tdb_info.get("publisher"))
                    
                    # Visuals - Try both camelCase (blawar) and snake_case (standard JSONs)
                    icon = tdb_info.get("iconUrl") or tdb_info.get("icon_url")
                    set_if_not_empty(title, "icon_url", icon)
                    
                    banner = tdb_info.get("bannerUrl") or tdb_info.get("banner_url")
                    set_if_not_empty(title, "banner_url", banner)

                    cat = tdb_info.get("category") or tdb_info.get("genre")
                    if cat:
                        title.category = ",".join(cat) if isinstance(cat, list) else str(cat)

                    # Date - Try both
                    release = tdb_info.get("releaseDate") or tdb_info.get("release_date")
                    set_if_not_empty(title, "release_date", release)
                    
                    if tdb_info.get("size"):
                        title.size = tdb_info.get("size")
                        
                    # Support both nsuid and nsuId
                    nsuid_val = tdb_info.get("nsuid") or tdb_info.get("nsuId")
                    if nsuid_val:
                        title.nsuid = str(nsuid_val)

                    # Update screenshots if available
                    ss = tdb_info.get("screenshots")
                    if ss and isinstance(ss, list):
                        title.screenshots_json = ss
                    
                    updated_count += 1
                
                # Periodic yield for safety
                if updated_count % 500 == 0:
                    yield_to_event_loop()

        db.session.commit()
        logger.info(f"Sync complete. Updated {updated_count} titles in database metadata tracker.")
    except Exception as e:
        logger.error(f"Error during TitleDB-to-DB sync: {e}")
        db.session.rollback()
