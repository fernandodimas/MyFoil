import hashlib
import json
import functools
import os
from pathlib import Path

from constants import APP_TYPE_BASE, APP_TYPE_UPD, APP_TYPE_DLC, LIBRARY_CACHE_FILE
from db import (
    db,
    Files,
    Apps,
    Titles,
    Tag,
    get_all_apps,
    get_title,
    get_all_title_apps,
)
from db import logger
import titles as titles_lib
from library._state import LIBRARY_CACHE
from utils import now_utc, safe_write_json
from models.titlemetadata import TitleMetadata


# Memory optimization: configurable cache settings
DISABLE_LIBRARY_CACHE = os.getenv("DISABLE_LIBRARY_CACHE", "false").lower() == "true"
LIBRARY_CACHE_MAX_SIZE = int(os.getenv("LIBRARY_CACHE_MAX_SIZE", "100"))


# Reduced cache sizes to save memory (was 4096 each)
@functools.lru_cache(maxsize=512)
def _cached_get_all_existing_dlc(tid):
    try:
        return titles_lib.get_all_existing_dlc(tid) or []
    except Exception:
        return []


@functools.lru_cache(maxsize=512)
def _cached_get_all_existing_versions(tid):
    try:
        return titles_lib.get_all_existing_versions(tid) or []
    except Exception:
        return []


@functools.lru_cache(maxsize=512)
def _cached_get_all_app_existing_versions(app_id):
    try:
        return titles_lib.get_all_app_existing_versions(app_id) or []
    except Exception:
        return []


def _clear_titledb_caches():
    try:
        _cached_get_all_existing_dlc.cache_clear()
    except Exception:
        pass
    try:
        _cached_get_all_existing_versions.cache_clear()
    except Exception:
        pass


def compute_apps_hash():
    """Compute hash using SQL aggregation instead of loading all data into memory"""
    from sqlalchemy import func
    hash_md5 = hashlib.md5(usedforsecurity=False)
    
    # Use COUNT queries instead of loading all rows
    apps_count = db.session.query(func.count(Apps.id)).scalar() or 0
    apps_max_id = db.session.query(func.max(Apps.id)).scalar() or 0
    apps_max_version = db.session.query(func.max(Apps.app_version)).scalar() or 0
    hash_md5.update(f"apps:{apps_count}:{apps_max_id}:{apps_max_version}".encode())
    
    # Count apps by type and owned status
    for app_type in ['BASE', 'UPD', 'DLC']:
        for owned in [True, False]:
            count = db.session.query(func.count(Apps.id)).filter(
                Apps.app_type == app_type, Apps.owned == owned
            ).scalar() or 0
            hash_md5.update(f"{app_type}:{owned}:{count}".encode())
    
    # Include Titles table in hash to detect up_to_date/have_base/complete changes
    titles_count = db.session.query(func.count(Titles.id)).scalar() or 0
    titles_max_id = db.session.query(func.max(Titles.id)).scalar() or 0
    titles_up_to_date_count = db.session.query(func.count(Titles.id)).filter(Titles.up_to_date == True).scalar() or 0
    titles_have_base_count = db.session.query(func.count(Titles.id)).filter(Titles.have_base == True).scalar() or 0
    titles_complete_count = db.session.query(func.count(Titles.id)).filter(Titles.complete == True).scalar() or 0
    hash_md5.update(f"titles:{titles_count}:{titles_max_id}:utd:{titles_up_to_date_count}:base:{titles_have_base_count}:complete:{titles_complete_count}".encode())
    
    tags_count = db.session.query(func.count(Tag.id)).scalar() or 0
    tags_max_id = db.session.query(func.max(Tag.id)).scalar() or 0
    hash_md5.update(f"tags:{tags_count}:{tags_max_id}".encode())
    
    meta_count = db.session.query(func.count(TitleMetadata.id)).scalar() or 0
    meta_max_id = db.session.query(func.max(TitleMetadata.id)).scalar() or 0
    hash_md5.update(f"meta:{meta_count}:{meta_max_id}".encode())
    
    from db import Files
    file_count = db.session.query(Files).filter(Files.identified == True).count()
    hash_md5.update(str(file_count).encode())
    
    return hash_md5.hexdigest()


def is_library_unchanged():
    cached_lib = load_library_from_disk()
    if not cached_lib:
        return False
    current_hash = compute_apps_hash()
    return cached_lib.get("hash") == current_hash


def save_library_to_disk(library_data):
    safe_write_json(LIBRARY_CACHE_FILE, library_data)


def load_library_from_disk():
    try:
        path = Path(LIBRARY_CACHE_FILE)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load library from disk: {e}")
    return None


def invalidate_library_cache():
    with LIBRARY_CACHE.lock:
        LIBRARY_CACHE.data = None
        LIBRARY_CACHE.hash = None
    try:
        path = Path(LIBRARY_CACHE_FILE)
        if path.exists():
            path.unlink()
    except Exception:
        pass


def detect_changed_titles(since_seconds=None):
    from datetime import timedelta
    from models.apps import app_files

    if since_seconds is None:
        since_seconds = 300
    cutoff_time = now_utc() - timedelta(seconds=since_seconds)
    changed = (
        db.session.query(Titles)
        .join(Apps, Titles.id == Apps.title_id)
        .join(app_files, Apps.id == app_files.c.app_id)
        .join(Files, Files.id == app_files.c.file_id)
        .filter(Files.last_attempt >= cutoff_time)
        .distinct()
        .all()
    )
    return [{"title_id": t.title_id, "name": t.name} for t in changed]


def get_library_status(title_id):
    title = get_title(title_id)
    if not title:
        return None

    all_apps = get_all_title_apps(title_id)
    has_base = any(a.app_type == APP_TYPE_BASE and a.owned for a in all_apps)

    all_versions = titles_lib.get_all_existing_versions(title_id)
    if all_versions:
        latest_version = max(v["version"] for v in all_versions)
        owned_updates = [a for a in all_apps if a.app_type == APP_TYPE_UPD and a.owned]
        has_latest = any(a.version == latest_version for a in owned_updates) if owned_updates else False
    else:
        latest_version = None
        has_latest = None

    all_dlc = titles_lib.get_all_existing_dlc(title_id)
    owned_dlc = [a for a in all_apps if a.app_type == APP_TYPE_DLC and a.owned]
    has_all_dlcs = len(owned_dlc) >= len(all_dlc) if all_dlc else None

    return {
        "has_base": has_base,
        "has_latest_version": has_latest,
        "version": latest_version,
        "has_all_dlcs": has_all_dlcs,
    }
