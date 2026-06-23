import hashlib
import json
import functools
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


@functools.lru_cache(maxsize=4096)
def _cached_get_all_existing_dlc(tid):
    try:
        return titles_lib.get_all_existing_dlc(tid) or []
    except Exception:
        return []


@functools.lru_cache(maxsize=4096)
def _cached_get_all_existing_versions(tid):
    try:
        return titles_lib.get_all_existing_versions(tid) or []
    except Exception:
        return []


@functools.lru_cache(maxsize=4096)
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
    hash_md5 = hashlib.md5(usedforsecurity=False)
    all_apps = get_all_apps()
    all_tags = db.session.query(Tag).order_by(Tag.id).all()
    all_metadata = db.session.query(TitleMetadata).order_by(TitleMetadata.id).all()

    for app in all_apps:
        hash_md5.update(str(app.get("id", "")).encode())
        hash_md5.update(str(app.get("title_id", "")).encode())
        hash_md5.update(str(app.get("app_id", "")).encode())
        hash_md5.update(str(app.get("app_type", "")).encode())
        hash_md5.update(str(app.get("owned", "")).encode())
        if app.get("app_version"):
            hash_md5.update(str(app["app_version"]).encode())

    for tag in all_tags:
        hash_md5.update(str(tag.id).encode())
        hash_md5.update(str(tag.name).encode())

    for meta in all_metadata:
        hash_md5.update(str(meta.title_id).encode())
        if meta.description:
            hash_md5.update(str(meta.description)[:200].encode())
        if meta.rating is not None:
            hash_md5.update(str(meta.rating).encode())
        if meta.genres:
            hash_md5.update(str(meta.genres).encode())
        if meta.screenshots:
            hash_md5.update(str(len(meta.screenshots)).encode())

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
