"""
TitleDB File-Based Cache
Provides fast compressed JSON file cache for TitleDB data
"""
import gzip
import json
import os
import logging
from typing import Dict, Optional
from constants import DATA_DIR
from utils import now_utc

logger = logging.getLogger("main")

TITLEDB_CACHE_FILE = os.path.join(DATA_DIR, "titledb_cache.json.gz")


def save_titledb_to_file(titles_db: dict, versions_db: dict = None, dlcs_db: dict = None) -> bool:
    """
    Save TitleDB to compressed JSON file
    
    Args:
        titles_db: Dictionary of title_id -> title data
        versions_db: Optional dictionary of title_id -> versions
        dlcs_db: Optional dictionary of title_id -> DLC list
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        cache_data = {
            "titles": titles_db,
            "versions": versions_db or {},
            "dlcs": dlcs_db or {},
            "cached_at": now_utc().isoformat(),
            "count": len(titles_db)
        }
        
        logger.info(f"Saving {len(titles_db)} titles to file cache...")
        
        with gzip.open(TITLEDB_CACHE_FILE, 'wt', encoding='utf-8') as f:
            json.dump(cache_data, f)
        
        file_size_mb = os.path.getsize(TITLEDB_CACHE_FILE) / (1024 * 1024)
        logger.info(f"✅ TitleDB file cache saved: {len(titles_db)} titles, {file_size_mb:.2f} MB compressed")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save titledb file cache: {e}", exc_info=True)
        return False


def load_titledb_from_file() -> Optional[Dict]:
    """
    Load TitleDB from compressed JSON file
    
    Returns:
        Dictionary with 'titles', 'versions', 'dlcs', 'cached_at', 'count'
        Returns None if file doesn't exist or is corrupted
    """
    if not os.path.exists(TITLEDB_CACHE_FILE):
        logger.debug("TitleDB file cache does not exist")
        return None
    
    try:
        file_size_mb = os.path.getsize(TITLEDB_CACHE_FILE) / (1024 * 1024)
        logger.info(f"Loading TitleDB from file cache ({file_size_mb:.2f} MB)...")
        
        with gzip.open(TITLEDB_CACHE_FILE, 'rt', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        title_count = cache_data.get('count', len(cache_data.get('titles', {})))
        logger.info(f"✅ Loaded {title_count} titles from file cache (cached at: {cache_data.get('cached_at', 'unknown')})")
        
        return cache_data
        
    except Exception as e:
        logger.error(f"Failed to load titledb file cache: {e}", exc_info=True)
        # Delete corrupted cache
        try:
            os.remove(TITLEDB_CACHE_FILE)
            logger.info("Removed corrupted file cache")
        except:
            pass
        return None


def is_file_cache_fresh(max_age_seconds: int = 3600) -> bool:
    """
    Check if file cache exists and is recent enough
    
    Args:
        max_age_seconds: Maximum age in seconds (default 1 hour)
        
    Returns:
        True if cache exists and is fresh, False otherwise
    """
    if not os.path.exists(TITLEDB_CACHE_FILE):
        return False
    
    try:
        import datetime
        from datetime import timezone
        
        file_mtime = os.path.getmtime(TITLEDB_CACHE_FILE)
        file_age = datetime.datetime.now(timezone.utc).timestamp() - file_mtime
        
        is_fresh = file_age < max_age_seconds
        logger.debug(f"File cache age: {file_age:.0f}s, fresh: {is_fresh}")
        return is_fresh
        
    except Exception as e:
        logger.warning(f"Could not check file cache freshness: {e}")
        return False
