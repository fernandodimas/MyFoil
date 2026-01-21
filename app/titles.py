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
    global _titles_db, _versions_db, _cnmts_db, _titledb_cache_timestamp, _titles_db_loaded

    try:
        from db import db, TitleDBCache, TitleDBVersions, TitleDBDLCs

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

        # Load DLCs from cache and build index
        _cnmts_db = {}
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

        # Clear old cache entries
        try:
            TitleDBCache.query.delete()
            TitleDBVersions.query.delete()
            TitleDBDLCs.query.delete()
            db.session.commit()
        except Exception as e:
            logger.warning(f"Could not clear old cache: {e}")
            db.session.rollback()

        # Batch insert titles
        title_entries = []
        for tid, data in _titles_db.items():
            title_entries.append(
                TitleDBCache(
                    title_id=tid,
                    data=data,
                    source=source_files.get(tid.lower(), "titles.json"),
                    downloaded_at=now,
                    updated_at=now,
                )
            )

        if title_entries:
            db.session.bulk_save_objects(title_entries)

        # Batch insert versions
        version_entries = []
        for tid, versions in (_versions_db or {}).items():
            for version_str, release_date in versions.items():
                try:
                    version_entries.append(
                        TitleDBVersions(title_id=tid, version=int(version_str), release_date=release_date)
                    )
                except (ValueError, TypeError):
                    continue

        if version_entries:
            db.session.bulk_save_objects(version_entries)

        # Batch insert DLCs
        dlc_entries = []
        for base_tid, dlcs in (_cnmts_db or {}).items():
            for dlc_app_id in dlcs.keys():
                dlc_entries.append(TitleDBDLCs(base_title_id=base_tid, dlc_app_id=dlc_app_id))

        if dlc_entries:
            db.session.bulk_save_objects(dlc_entries)

        db.session.commit()
        _titledb_cache_timestamp = time.time()  # Use time.time() for cache TTL comparison
        logger.info(
            f"TitleDB saved to DB cache: {len(title_entries)} titles, {len(version_entries)} versions, {len(dlc_entries)} DLCs"
        )
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

    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            content = f.read()
            if not content:
                return None
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")
        return None

    # Try 1: Standard load - fast and correct
    try:
        data = json.loads(content)
        return (
            data
            if not isinstance(data, dict)
            else (data.get("data") or data.get("items") or data.get("titles") or data)
        )
    except json.JSONDecodeError:
        pass

    # Try 2: More aggressive sanitization for escape sequences
    logger.warning(f"JSON error in {filepath}, attempting aggressive sanitization...")
    try:
        # Pattern to match a valid escape or a bare backslash
        # Group 1 captures valid escape sequences: \", \\, \/, \b, \f, \n, \r, \t, or \uXXXX
        pattern = re.compile(r"(\\([\"\\/bfnrt]|u[0-9a-fA-F]{4}))|(\\)")

        def replace_func(m):
            if m.group(1):
                return m.group(1)  # Valid escape, keep it
            else:
                return r"\\"  # Bare backslash, escape it

        sanitized = pattern.sub(replace_func, content)

        # Strip ALL non-printable control characters except whitespace
        sanitized = "".join(ch for ch in sanitized if ord(ch) >= 32 or ch in "\n\r\t")

        # Try loading the sanitized version
        data = json.loads(sanitized, strict=False)
        return (
            data
            if not isinstance(data, dict)
            else (data.get("data") or data.get("items") or data.get("titles") or data)
        )
    except Exception as e:
        logger.error(f"Aggressive sanitization failed for {filepath}: {e}")

    # Try 3: Nuclear Cleanup - if still failing, it's likely structural or has nested escape issues
    try:
        # Bruteforce: replace all \ with \\ then restore common escapes
        # This fixes bare backslashes but we MUST restore valid sequences or it will remain invalid
        nuclear = content.replace("\\", "\\\\")
        for escape in ['"', "\\", "/", "b", "f", "n", "r", "t"]:
            nuclear = nuclear.replace("\\\\" + escape, "\\" + escape)
        # Restore unicode
        nuclear = re.sub(r"\\\\u([0-9a-fA-F]{4})", r"\\u\1", nuclear)

        nuclear = "".join(ch for ch in nuclear if ord(ch) >= 32 or ch in "\n\r\t")
        data = json.loads(nuclear, strict=False)
        return (
            data
            if not isinstance(data, dict)
            else (data.get("data") or data.get("items") or data.get("titles") or data)
        )
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
        pattern = re.compile(r"\"([0-9A-F]{16})\":\s*\{")

        # We need the full content for this
        parts = pattern.split(content)
        # parts[0] is garbage or opening brace
        # parts[1] is ID, parts[2] is Body, etc.

        for i in range(1, len(parts), 2):
            tid = parts[i]
            body = parts[i + 1]

            # Find the end of this object (the last closing brace)
            last_brace = body.rfind("}")
            if last_brace != -1:
                clean_body = "{" + body[: last_brace + 1]
                try:
                    # Try to parse this individual object
                    obj = json.loads(clean_body, strict=False)
                    recovered[tid] = obj
                except:
                    # Partial cleanup for the chunk
                    try:
                        # Basic escape fix for the chunk
                        chunk_sanitized = re.sub(r'\\(?!(["\\/bfnrt]|u[0-9a-fA-F]{4}))', r"\\\\", clean_body)
                        obj = json.loads(chunk_sanitized, strict=False)
                        recovered[tid] = obj
                    except:
                        continue  # Skip this specific corrupt entry

        if len(recovered) > 0:
            logger.info(
                f"Chunked recovery successful! Salvaged {len(recovered)} entries from corrupted file {filepath}."
            )
            return recovered
    except Exception as e:
        logger.error(f"Chunked recovery failed for {filepath}: {e}")

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

    global _cnmts_db
    if _cnmts_db is None:
        logger.error("cnmts_db is not loaded. Call load_titledb first.")
        return None, None

    if app_id in _cnmts_db:
        app_id_keys = list(_cnmts_db[app_id].keys())
        if len(app_id_keys):
            app = _cnmts_db[app_id][app_id_keys[-1]]

            if app["titleType"] == 128:
                app_type = APP_TYPE_BASE
                title_id = app_id.upper()
            elif app["titleType"] == 129:
                app_type = APP_TYPE_UPD
                if "otherApplicationId" in app:
                    title_id = app["otherApplicationId"].upper()
                else:
                    title_id = get_title_id_from_app_id(app_id, app_type)
            elif app["titleType"] == 130:
                app_type = APP_TYPE_DLC
                if "otherApplicationId" in app:
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

    return title_id.upper(), app_type


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
        region = app_settings["titles"].get("region", "US")
        language = app_settings["titles"].get("language", "en")
        possible_files = titledb.get_region_titles_filenames(region, language) + [
            "titles.US.en.json",
            "US.en.json",
            "titles.json",
        ]

        _titles_db = {}
        global _loaded_titles_file
        _loaded_titles_file = []  # Now a list of files loaded

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
                        is_custom = filename == "custom.json"
                        # Convert list to dict if necessary for merging
                        current_batch = {}
                        if isinstance(loaded, list):
                            for item in loaded:
                                if isinstance(item, dict) and "id" in item:
                                    current_batch[item["id"].upper()] = item
                        else:
                            current_batch = {k.upper(): v for k, v in loaded.items() if isinstance(v, dict)}

                        # MERGE logic: Keep metadata (urls, size, etc) but update names/descriptions
                        if not _titles_db:
                            _titles_db = current_batch
                        else:
                            for tid, data in current_batch.items():
                                if tid in _titles_db:
                                    if is_custom:
                                        # For custom.json, merge EVERYTHING to ensure manual overrides persist
                                        _titles_db[tid].update(data)
                                    else:
                                        # Override specific fields but keep the rest
                                        for field in [
                                            "name",
                                            "description",
                                            "bannerUrl",
                                            "iconUrl",
                                            "publisher",
                                            "releaseDate",
                                            "size",
                                            "category",
                                            "genre",
                                            "release_date",
                                        ]:
                                            val = data.get(field)
                                            if val is not None and val != "":
                                                _titles_db[tid][field] = val
                                else:
                                    _titles_db[tid] = data

                        _loaded_titles_file.append(filename)
                        logger.info(
                            f"SUCCESS: Merged {count} items from {filename} {'(AS OVERRIDE)' if is_custom else ''}"
                        )
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
        _versions_db = robust_json_load(_versions_db_path) or {}
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
                "bannerUrl": info.get("bannerUrl") or "",
                "iconUrl": info.get("iconUrl") or "",
                "id": info.get("id") or title_id,
                "category": info.get("category", [])
                if isinstance(info.get("category"), list)
                else [info.get("category")]
                if info.get("category")
                else [],
                "release_date": format_release_date(info.get("releaseDate")),
                "size": info.get("size") or 0,
                "publisher": info.get("publisher") or "Nintendo",
                "description": info.get("description") or "",
                "nsuid": info.get("nsuid") or "",
                "screenshots": info.get("screenshots", []),
            }

            # DLC/Update Icon Fallback: If icon is missing, try to inherit from base game
            if (not res["iconUrl"] or res["iconUrl"] == "") and not search_id.endswith("000"):
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
            if (not res["iconUrl"] or res["iconUrl"] == "") and res["bannerUrl"]:
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
        return {
            "name": f"Unknown ({title_id})",
            "bannerUrl": "",
            "iconUrl": "",
            "id": title_id.upper(),
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


def get_loaded_titles_file():
    global _loaded_titles_file
    if isinstance(_loaded_titles_file, list):
        # Prefer showing the most specific/regional file if multiple were merged
        # The regional ones are at the end of the load_order
        for f in reversed(_loaded_titles_file):
            if "." in f and any(ext in f.lower() for ext in [".br", "pt", "pt.json", "br.json"]):
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
            if (
                version_description.get("titleType") == 130
                and version_description.get("otherApplicationId") == title_id
            ):
                if app_id.upper() not in dlcs:
                    dlcs.append(app_id.upper())
    return dlcs


def get_loaded_titles_file():
    """Return the filename of the currently loaded titles database"""
    global _loaded_titles_file
    return _loaded_titles_file


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

        db_titles_map = {t.title_id.upper(): t for t in db_titles}

        updated_count = 0
        for tid, tdb_info in _titles_db.items():
            tid = tid.upper()
            if tid in db_titles_map:
                title = db_titles_map[tid]

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

        db.session.commit()
        logger.info(f"Sync complete. Updated {updated_count} titles in database.")
    except Exception as e:
        logger.error(f"Error during TitleDB-to-DB sync: {e}")
        db.session.rollback()
