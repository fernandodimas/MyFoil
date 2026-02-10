"""
Redis Cache Module for MyFoil
Provides caching layer for frequently accessed endpoints with graceful degradation
"""

import os
import json
import logging
import hashlib
import functools
from datetime import datetime, timedelta
from typing import Any, Optional, Callable, Dict, List

logger = logging.getLogger(__name__)

redis_client = None
_cache_stats = {
    "hits": 0,
    "misses": 0,
    "sets": 0,
    "deletes": 0,
}

try:
    import redis

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    redis_client = redis.from_url(redis_url, decode_responses=True)
    try:
        redis_client.ping()
        logger.info(f"Redis cache initialized at {redis_url}")
    except Exception as e:
        logger.warning(f"Redis cache initialized but ping failed: {e}. Cache will be disabled.")
        redis_client = None
except ImportError:
    logger.warning("Redis module not installed. Cache will be disabled.")
except Exception as e:
    logger.warning(f"Redis cache initialization failed: {e}. Cache will be disabled.")


def is_cache_enabled() -> bool:
    """Check if Redis cache is enabled and available"""
    return redis_client is not None


def get_cache_stats() -> Dict:
    """Get cache statistics (hits, misses, sets, deletes)"""
    if redis_client:
        return {**_cache_stats}
    return {"status": "disabled"}


def reset_cache_stats() -> None:
    """Reset cache statistics"""
    _cache_stats["hits"] = 0
    _cache_stats["misses"] = 0
    _cache_stats["sets"] = 0
    _cache_stats["deletes"] = 0


def make_cache_key(prefix: str, *args, **kwargs) -> str:
    """
    Generate a cache key from function arguments

    Args:
        prefix: Prefix for the cache key (e.g., "library", "system_info")
        *args: Positional arguments to include in key
        **kwargs: Keyword arguments to include in key

    Returns:
        Cache key string
    """
    key_parts = [prefix]

    for arg in args:
        if hasattr(arg, "__dict__"):
            key_parts.append(str(hashlib.md5(json.dumps(arg.__dict__, sort_keys=True).encode()).hexdigest()))
        else:
            key_parts.append(str(arg))

    for k, v in sorted(kwargs.items()):
        if hasattr(v, "__dict__"):
            key_parts.append(f"{k}={hashlib.md5(json.dumps(v.__dict__, sort_keys=True).encode()).hexdigest()}")
        else:
            key_parts.append(f"{k}={v}")

    return ":".join(key_parts)


def cache_get(key: str) -> Optional[str]:
    """
    Get a value from cache

    Args:
        key: Cache key

    Returns:
        Cached value or None if not found
    """
    if not redis_client:
        return None
    try:
        value = redis_client.get(key)
        if value:
            _cache_stats["hits"] += 1
            logger.debug(f"Cache HIT: {key}")
            return value
        else:
            _cache_stats["misses"] += 1
            logger.debug(f"Cache MISS: {key}")
            return None
    except Exception as e:
        logger.warning(f"Cache get error for {key}: {e}")
        return None


def cache_set(key: str, value: Any, ttl: int = 300) -> bool:
    """
    Set a value in cache with TTL

    Args:
        key: Cache key
        value: Value to cache (must be JSON-serializable)
        ttl: Time to live in seconds (default: 300 = 5 min)

    Returns:
        True if set successfully, False otherwise
    """
    if not redis_client:
        return False
    try:
        if not isinstance(value, str):
            value = json.dumps(value)
        redis_client.setex(key, ttl, value)
        _cache_stats["sets"] += 1
        logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
        return True
    except Exception as e:
        logger.warning(f"Cache set error for {key}: {e}")
        return False


def cache_delete(key: str) -> bool:
    """
    Delete a value from cache

    Args:
        key: Cache key

    Returns:
        True if deleted successfully, False otherwise
    """
    if not redis_client:
        return False
    try:
        result = redis_client.delete(key)
        if result > 0:
            _cache_stats["deletes"] += 1
            logger.debug(f"Cache DELETE: {key}")
        return result > 0
    except Exception as e:
        logger.warning(f"Cache delete error for {key}: {e}")
        return False


def cache_delete_pattern(pattern: str) -> int:
    """
    Delete multiple keys matching a pattern

    Args:
        pattern: Redis key pattern (e.g., "library:*", "system:*")

    Returns:
        Number of keys deleted
    """
    if not redis_client:
        return 0
    try:
        keys = redis_client.keys(pattern)
        if keys:
            count = redis_client.delete(*keys)
            _cache_stats["deletes"] += count
            logger.info(f"Cache DELETE: {pattern} ({count} keys)")
            return count
        return 0
    except Exception as e:
        logger.warning(f"Cache delete pattern error for {pattern}: {e}")
        return 0


def cached(ttl: int = 300, prefix: Optional[str] = None):
    """
    Decorator to cache function results

    Args:
        ttl: Time to live in seconds (default: 300 = 5 min)
        prefix: Cache key prefix (defaults to function name)

    Usage:
        @cached(ttl=300, prefix="library")
        def get_library():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not redis_client:
                return func(*args, **kwargs)

            cache_key = make_cache_key(prefix or func.__name__, *args, **kwargs)

            cached_value = cache_get(cache_key)
            if cached_value:
                try:
                    return json.loads(cached_value)
                except json.JSONDecodeError:
                    pass

            result = func(*args, **kwargs)

            cache_set(cache_key, result, ttl)

            return result

        return wrapper

    return decorator


def invalidate_library_cache() -> bool:
    """
    Invalidate all library-related cache entries

    Returns:
        True if cache was cleared (or cache disabled), False on error
    """
    if not redis_client:
        return True

    try:
        patterns = [
            "library:*",
            "library_paged:*",
            "library_search:*",
            "titles:*",
        ]

        total_deleted = 0
        for pattern in patterns:
            total_deleted += cache_delete_pattern(pattern)

        if total_deleted > 0:
            logger.info(f"Invalidated {total_deleted} library cache entries")
        return True
    except Exception as e:
        logger.error(f"Error invalidating library cache: {e}")
        return False


def invalidate_system_cache() -> bool:
    """
    Invalidate all system-related cache entries

    Returns:
        True if cache was cleared (or cache disabled), False on error
    """
    if not redis_client:
        return True

    try:
        patterns = [
            "system:*",
            "stats:*",
        ]

        total_deleted = 0
        for pattern in patterns:
            total_deleted += cache_delete_pattern(pattern)

        if total_deleted > 0:
            logger.info(f"Invalidated {total_deleted} system cache entries")
        return True
    except Exception as e:
        logger.error(f"Error invalidating system cache: {e}")
        return False


def clear_all_cache() -> bool:
    """
    Clear all cache entries in Redis (use with caution!)

    Returns:
        True if cache was cleared (or cache disabled), False on error
    """
    if not redis_client:
        return True

    try:
        count = 0
        for key in redis_client.scan_iter():
            redis_client.delete(key)
            count += 1

        _cache_stats["deletes"] += count
        logger.info(f"Cleared all cache entries ({count} keys)")
        return True
    except Exception as e:
        logger.error(f"Error clearing all cache: {e}")
        return False


def get_cache_info() -> Dict:
    """
    Get detailed cache information

    Returns:
        Dictionary with cache status, stats, and key count
    """
    if not redis_client:
        return {"status": "disabled", "error": "Redis not available"}

    try:
        key_count = len(list(redis_client.scan_iter()))
        return {
            "status": "enabled",
            "keys": key_count,
            "stats": get_cache_stats(),
            "redis_url": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
