import os
import json
import time
import fcntl

try:
    import gevent
except ImportError:
    gevent = None


def _safe_sleep(seconds):
    """Sleep using gevent if available, otherwise time.sleep"""
    if gevent:
        gevent.sleep(seconds)
    else:
        time.sleep(seconds)

import titles._state as _state
from titles._state import logger
from titles.utils import robust_json_load
from constants import TITLEDB_DIR, CONFIG_DIR
from utils import now_utc
from settings import load_settings


def get_titles_count():
    return len(_state._titles_db) if _state._titles_db else 0


def get_titles_type_breakdown():
    """Count titles by type: games (base), DLCs, updates, unmatched"""
    if not _state._titles_db:
        return {"games": 0, "dlcs": 0, "updates": 0, "unmatched": 0, "total": 0}

    # Collect all known DLC app IDs from multiple sources
    known_dlcs = set()
    if _state._dlc_map:
        known_dlcs.update(k.upper() for k in _state._dlc_map.keys())
    if _state._dlcs_by_base_id:
        for dlc_ids in _state._dlcs_by_base_id.values():
            for d in dlc_ids:
                known_dlcs.add(d.upper())
    if _state._cnmts_db:
        for app_id, versions in _state._cnmts_db.items():
            if isinstance(versions, dict):
                for vdata in versions.values():
                    if isinstance(vdata, dict) and vdata.get("titleType") == 130:
                        known_dlcs.add(app_id.upper())

    # Count unmatched titles from DB
    unmatched = 0
    try:
        from db import Titles
        from db import db as _db
        unmatched = Titles.query.filter(
            Titles.rawg_id.is_(None),
            Titles.igdb_id.is_(None),
            Titles.api_source.is_(None),
        ).count()
    except Exception:
        pass

    games = 0
    dlcs = 0
    updates = 0

    for tid_upper, tdata in _state._titles_db.items():
        if not isinstance(tdata, dict):
            continue
        tid = tid_upper.upper() if isinstance(tid_upper, str) else str(tid_upper).upper()
        if len(tid) != 16:
            continue

        if tid.endswith("800"):
            updates += 1
        elif tid in known_dlcs or tdata.get("parentId"):
            dlcs += 1
        else:
            games += 1

    return {"games": games, "dlcs": dlcs, "updates": updates, "unmatched": unmatched, "total": games + dlcs + updates}


def _enrich_dlc_map_from_titles():
    if not _state._titles_db:
        return
    inferred = 0
    for tid_upper, tdata in list(_state._titles_db.items()):
        if len(tid_upper) == 16 and not tid_upper.endswith("000") and not tid_upper.endswith("800"):
            base_candidate = tid_upper[:12] + "8000"
            if base_candidate in _state._titles_db and base_candidate != tid_upper:
                if tid_upper not in _state._dlc_map:
                    _state._dlc_map[tid_upper] = base_candidate
                base_lower = base_candidate.lower()
                if base_lower not in _state._dlcs_by_base_id:
                    _state._dlcs_by_base_id[base_lower] = []
                if tid_upper not in _state._dlcs_by_base_id[base_lower]:
                    _state._dlcs_by_base_id[base_lower].append(tid_upper)
                    inferred += 1
    if inferred:
        logger.info(f"  Inferred {inferred} additional DLC mappings from title ID patterns")


def load_titledb_from_db():
    logger.info("Loading TitleDB from PostgreSQL database...")

    try:
        from db import TitleDBCache, TitleDBVersions, TitleDBDLCs

        try:
            cache_count = TitleDBCache.query.count()
            if cache_count == 0:
                logger.info("TitleDB cache is empty, will load from files")
                return False
        except Exception as e:
            logger.warning(f"TitleDB cache tables don't exist yet: {e}")
            return False

        logger.info(f"Loading TitleDB from database cache ({cache_count} titles)...")
        cached_titles = TitleDBCache.query.all()

        _state._titles_db = {}
        for entry in cached_titles:
            if entry.title_id:
                _state._titles_db[entry.title_id.upper()] = entry.data

        cached_versions = TitleDBVersions.query.all()
        _state._versions_db = {}
        for entry in cached_versions:
            if entry.title_id:
                tid = entry.title_id.lower()
                if tid not in _state._versions_db:
                    _state._versions_db[tid] = {}
                _state._versions_db[tid][str(entry.version)] = entry.release_date

        _state._cnmts_db = {}
        _state._dlc_map = {}
        _state._dlcs_by_base_id = {}
        cached_dlcs = TitleDBDLCs.query.all()
        for entry in cached_dlcs:
            if not entry.base_title_id or not entry.dlc_app_id:
                continue
            base_tid = entry.base_title_id.lower()
            dlc_app_id = entry.dlc_app_id.upper()

            dlc_id_lower = dlc_app_id.lower()
            if dlc_id_lower not in _state._cnmts_db:
                _state._cnmts_db[dlc_id_lower] = {}
            _state._cnmts_db[dlc_id_lower]["0"] = {
                "titleType": 130,
                "otherApplicationId": base_tid,
            }
            _state._dlc_map[dlc_app_id] = base_tid

            if base_tid not in _state._dlcs_by_base_id:
                _state._dlcs_by_base_id[base_tid] = []
            if dlc_app_id not in _state._dlcs_by_base_id[base_tid]:
                _state._dlcs_by_base_id[base_tid].append(dlc_app_id)

        for tid, data in _state._titles_db.items():
            if isinstance(data, dict) and data.get("parentId"):
                base_tid = str(data["parentId"]).lower()
                dlc_app_id = tid.upper()

                dlc_id_lower = dlc_app_id.lower()
                if dlc_id_lower not in _state._cnmts_db:
                    _state._cnmts_db[dlc_id_lower] = {}
                    _state._cnmts_db[dlc_id_lower]["0"] = {
                        "titleType": 130,
                        "otherApplicationId": base_tid,
                    }

                if dlc_app_id not in _state._dlc_map:
                    _state._dlc_map[dlc_app_id] = base_tid

                if base_tid not in _state._dlcs_by_base_id:
                    _state._dlcs_by_base_id[base_tid] = []
                if dlc_app_id not in _state._dlcs_by_base_id[base_tid]:
                    _state._dlcs_by_base_id[base_tid].append(dlc_app_id)

        _state._titles_db_loaded = True
        _state._titledb_cache_timestamp = time.time()
        logger.info(
            f"TitleDB loaded from DB cache: {len(_state._titles_db)} titles, {len(_state._versions_db)} versions, {len(cached_dlcs)} DLCs"
        )
        return True

    except Exception as e:
        logger.error(f"Error loading TitleDB from cache: {e}")
        return False


def save_titledb_to_db(source_files, app_context=None, progress_callback=None):
    try:
        from flask import has_app_context

        if not has_app_context():
            logger.warning("Cannot save TitleDB cache: no app context")
            return False

        from db import db, TitleDBCache, TitleDBVersions, TitleDBDLCs

        lock_path = os.path.join(CONFIG_DIR, ".titledb_save.lock")
        lock_file = open(lock_path, "w")
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, IOError):
            logger.info("Outro processo já está salvando o TitleDB no cache. Ignorando esta execução.")
            lock_file.close()
            return True

        logger.info("Saving TitleDB to database cache...")

        now = now_utc()

        from sqlalchemy.exc import OperationalError

        logger.info("Using UPSERT pattern (ON CONFLICT)")

        max_retries = 3
        retry_delay = 2

        try:
            import gevent
        except ImportError:
            gevent = None

        seen_titles = set()
        pending_entries = []
        BATCH_SIZE = 500

        logger.info(f"Starting to process {len(_state._titles_db)} titles in batches of {BATCH_SIZE}...")
        for i, (tid, data) in enumerate(_state._titles_db.items()):
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
                            wait_time = retry_delay * (2**attempt)
                            logger.warning(
                                f"DB locked during bulk save (attempt {attempt + 1}/{max_retries}). Retrying in {wait_time}s..."
                            )
                            db.session.rollback()
                            _safe_sleep(wait_time)
                            continue
                        raise
                    except Exception as e:
                        logger.error(f"Error during bulk save: {e}")
                        db.session.rollback()
                        raise
                pending_entries = []

                if progress_callback:
                    prog = 81 + int((i / len(_state._titles_db)) * 10)
                    progress_callback(f"Salvando títulos no cache ({i}/{len(_state._titles_db)})...", prog)

                if gevent:
                    gevent.sleep(0.01)

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
                        wait_time = retry_delay * (2**attempt)
                        logger.warning(
                            f"DB locked during final bulk save (attempt {attempt + 1}/{max_retries}). Retrying in {wait_time}s..."
                        )
                        db.session.rollback()
                        _safe_sleep(wait_time)
                        continue
                    raise
                except Exception as e:
                    logger.error(f"Error during final bulk save: {e}")
                    db.session.rollback()
                    raise
            pending_entries = []

        version_entries = []

        seen_versions = set()

        version_items = list((_state._versions_db or {}).items())
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

                    if len(version_entries) >= 500:
                        for attempt in range(max_retries):
                            try:
                                db.session.bulk_save_objects(version_entries)
                                db.session.commit()
                                break
                            except OperationalError as e:
                                if "locked" in str(e).lower() and attempt < max_retries - 1:
                                    logger.warning(f"DB locked during versions bulk save (attempt {attempt + 1})...")
                                    db.session.rollback()
                                    _safe_sleep(retry_delay)
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
                        logger.warning(f"DB locked during final versions bulk save (attempt {attempt + 1})...")
                        db.session.rollback()
                        _safe_sleep(retry_delay)
                        continue
                    raise
        version_entries = []

        dlc_entries = []
        seen_dlcs = set()

        cnmts_items = list((_state._cnmts_db or {}).items())
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
                                logger.warning(f"DB locked during DLC bulk save (attempt {attempt + 1})...")
                                db.session.rollback()
                                _safe_sleep(retry_delay)
                                continue
                            raise
                    dlc_entries = []
                    if gevent:
                        gevent.sleep(0.01)

        if dlc_entries:
            for attempt in range(max_retries):
                try:
                    db.session.bulk_save_objects(dlc_entries)
                    db.session.commit()
                    break
                except OperationalError as e:
                    if "locked" in str(e).lower() and attempt < max_retries - 1:
                        logger.warning(f"DB locked during final DLC bulk save (attempt {attempt + 1})...")
                        db.session.rollback()
                        _safe_sleep(retry_delay)
                        continue
                    raise
            dlc_entries = []

        version_count = len(seen_versions)
        dlc_count = len(seen_dlcs)

        _state._titledb_cache_timestamp = time.time()
        logger.info(f"TitleDB saved to DB cache: {title_count} titles, {version_count} versions, {dlc_count} DLCs")

        return True

    except Exception as e:
        logger.error(f"Error saving TitleDB to cache: {e}")
        try:
            db.session.rollback()
        except Exception as e:
            logger.debug(f"Rollback failed: {e}")
        return False
    finally:
        try:
            if "lock_file" in locals() and not lock_file.closed:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
                lock_file.close()
        except (OSError, ValueError) as e:
            logger.debug(f"Lock cleanup failed: {e}")


def is_db_cache_valid():
    if _state._titledb_cache_timestamp is None:
        return False

    age = time.time() - _state._titledb_cache_timestamp
    return age < _state._titledb_cache_ttl


def get_titledb_cache_timestamp():
    return _state._titledb_cache_timestamp


def set_titledb_cache_timestamp(timestamp):
    _state._titledb_cache_timestamp = timestamp


def load_titledb_from_disk_fallback():
    logger.info("TitleDB cache empty. Attempting fallback load from JSON files on disk...")

    try:
        app_settings = load_settings()
        region = app_settings.get("titles", {}).get("region", "US")
        language = app_settings.get("titles", {}).get("language", "en")
    except Exception:
        region, language = "US", "en"

    region_file = f"{region}.{language}.json"

    title_files_to_try = ["titles.json", "US.en.json", region_file]
    visited = set()
    for filename in title_files_to_try:
        filepath = os.path.join(TITLEDB_DIR, filename)
        if not os.path.exists(filepath) or filename in visited:
            continue
        visited.add(filename)
        try:
            data = robust_json_load(filepath)
            if not data or not isinstance(data, dict):
                continue
            loaded = 0
            for raw_tid, tdata in data.items():
                actual_tid = raw_tid
                if len(raw_tid) < 16 and isinstance(tdata, dict) and tdata.get("id"):
                    actual_tid = tdata["id"]
                if actual_tid:
                    _state._titles_db[actual_tid.upper()] = tdata
                    loaded += 1
            logger.info(f"  Loaded {loaded} titles from {filename}")
        except Exception as e:
            logger.warning(f"  Failed to load {filename} as fallback: {e}")

    versions_path = os.path.join(TITLEDB_DIR, "versions.json")
    if os.path.exists(versions_path):
        try:
            data = robust_json_load(versions_path)
            if data and isinstance(data, dict):
                for tid, v_dict in data.items():
                    tid_lower = tid.lower()
                    if tid_lower not in _state._versions_db:
                        _state._versions_db[tid_lower] = {}
                    for v_str, rdate in v_dict.items():
                        _state._versions_db[tid_lower][str(v_str)] = str(rdate) if rdate else ""
                logger.info(f"  Loaded {len(data)} version entries from versions.json")
        except Exception as e:
            logger.warning(f"  Failed to load versions.json: {e}")

    cnmts_path = os.path.join(TITLEDB_DIR, "cnmts.json")
    if os.path.exists(cnmts_path):
        try:
            data = robust_json_load(cnmts_path)
            if data and isinstance(data, dict):
                dlc_count = 0
                for tid, versions in data.items():
                    for v_str, info in versions.items():
                        if info.get("titleType") == 130 and info.get("otherApplicationId"):
                            base_tid = info["otherApplicationId"]
                            dlc_id = tid.upper()
                            _state._dlc_map[dlc_id] = base_tid
                            base_lower = base_tid.lower()
                            if base_lower not in _state._dlcs_by_base_id:
                                _state._dlcs_by_base_id[base_lower] = []
                            if dlc_id not in _state._dlcs_by_base_id[base_lower]:
                                _state._dlcs_by_base_id[base_lower].append(dlc_id)
                            dlc_count += 1
                logger.info(f"  Loaded {dlc_count} DLC mappings from cnmts.json")
        except Exception as e:
            logger.warning(f"  Failed to load cnmts.json: {e}")

    if _state._titles_db:
        _enrich_dlc_map_from_titles()
        _state._titledb_cache_timestamp = time.time()
        logger.info(
            f"TitleDB fallback loaded: {len(_state._titles_db)} titles, {len(_state._versions_db or {})} versions, {len(_state._dlc_map)} DLCs from disk"
        )
        return True

    logger.warning("TitleDB fallback: no titles could be loaded from disk")
    return False


def load_titledb(force=False, progress_callback=None):
    current_time = time.time()
    cache_expired = False
    if _state._titledb_cache_timestamp is not None:
        try:
            app_settings = load_settings()
            _state._titledb_cache_ttl = app_settings.get("titledb", {}).get("cache_ttl", 3600)
        except Exception:
            pass

        elapsed = current_time - _state._titledb_cache_timestamp
        if elapsed > _state._titledb_cache_ttl:
            cache_expired = True
            logger.info("TitleDB cache expired. Reloading...")

    if force or cache_expired:
        _state._titles_db_loaded = False
        _state._titledb_cache_timestamp = None

    if _state._titles_db_loaded:
        return

    logger.info("Loading TitleDB from database...")
    if progress_callback:
        progress_callback("Carregando banco de dados de títulos...", 10)

    if load_titledb_from_db():
        _state._titles_db_loaded = True
        logger.info("TitleDB loaded successfully from DB.")

        _enrich_dlc_map_from_titles()

        try:
            from titles.game_info import sync_titles_to_db
            sync_titles_to_db()
        except Exception as sync_err:
            logger.warning(f"Metadata sync after load failed: {sync_err}")
    else:
        logger.warning("Failed to load TitleDB from database (or empty).")
        if not load_titledb_from_disk_fallback():
            logger.warning("TitleDB disk fallback also failed. Titles will remain unnamed.")
            if _state._titles_db is None:
                _state._titles_db = {}
        if _state._versions_db is None:
            _state._versions_db = {}
        if _state._cnmts_db is None:
            _state._cnmts_db = {}
        if _state._dlc_map is None:
            _state._dlc_map = {}
        _state._titles_db_loaded = True


def unload_titledb():
    if _state.identification_in_progress_count:
        logger.debug("Identification still in progress, not unloading TitleDB.")
        return

    logger.info("Unloading TitleDBs from memory...")
    _state._cnmts_db = None
    _state._titles_db = None
    _state._versions_db = None
    _state._dlcs_by_base_id = {}
    _state._titles_db_loaded = False
    _state._titledb_cache_timestamp = None
    _state._game_info_cache = {}
    logger.info("TitleDBs unloaded.")
