"""
GitHub API Cache Module for TitleDB
Avoids redundant API calls to prevent rate limiting
"""

import time
import threading
import logging
from datetime import datetime
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# Global cache to avoid redundant GitHub API calls
# Key: (user, repo, branch, filepath) -> Value: (datetime, timestamp)
_GITHUB_API_CACHE: Dict[str, Tuple[datetime, float]] = {}
_GITHUB_API_LOCK = threading.Lock()


def _get_github_cache_key(user: str, repo: str, branch: str, filepath: str) -> str:
    """Generate a cache key for GitHub API requests"""
    return f"{user}:{repo}:{branch}:{filepath}"


def get_github_date_cached(
    api_url: str, headers: Dict, max_cache_age: int = 43200, delay_between_calls: float = 1.0
) -> Optional[datetime]:
    """
    Get GitHub commit date with caching to avoid rate limit

    Args:
        api_url: API endpoint URL
        headers: Request headers
        max_cache_age: Maximum cache age in seconds (default: 5 minutes)
        delay_between_calls: Delay in seconds between API calls

    Returns:
        datetime of last commit or None
    """
    import requests

    global _GITHUB_API_CACHE, _GITHUB_API_LOCK

    # Extract user, repo, branch, filepath from api_url
    # api_url format: https://api.github.com/repos/{user}/{repo}/commits?path={filepath}&sha={branch}&per_page=1
    try:
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(api_url)
        path_parts = parsed.path.split("/")
        if len(path_parts) < 5:
            return None

        user = path_parts[2]
        repo = path_parts[3]
        query_params = parse_qs(parsed.query)
        filepath = query_params.get("path", [""])[0]
        branch = query_params.get("sha", [""])[0]

        if not filepath or not branch:
            return None

        cache_key = _get_github_cache_key(user, repo, branch, filepath)
        current_time = time.time()

        # Check cache
        with _GITHUB_API_LOCK:
            if cache_key in _GITHUB_API_CACHE:
                cached_date, cached_time = _GITHUB_API_CACHE[cache_key]
                age = current_time - cached_time
                if age < max_cache_age:
                    logger.debug(f"Using cached GitHub API result for {cache_key} (age: {age:.1f}s)")
                    return cached_date
                else:
                    # Cache expired
                    del _GITHUB_API_CACHE[cache_key]

        # Add delay to prevent rate limiting from rapid successive calls
        time.sleep(delay_between_calls)

        # Make API request
        resp = requests.get(api_url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list) and len(data) > 0:
                commit_date = data[0]["commit"]["committer"]["date"]
                last_commit_date = datetime.fromisoformat(commit_date.replace("Z", "+00:00"))

                # Cache the result
                with _GITHUB_API_LOCK:
                    _GITHUB_API_CACHE[cache_key] = (last_commit_date, current_time)

                return last_commit_date
        elif resp.status_code == 403:
            # Rate limited
            logger.warning(f"GitHub API rate limited for {user}/{repo}")
            return None
    except Exception as e:
        logger.debug(f"GitHub API error: {e}")

    return None


def clear_github_api_cache():
    """Clear the GitHub API cache (useful for testing)"""
    global _GITHUB_API_CACHE, _GITHUB_API_LOCK
    with _GITHUB_API_LOCK:
        _GITHUB_API_CACHE.clear()
        logger.info("GitHub API cache cleared")


def get_github_cache_stats() -> Dict:
    """Get statistics about the GitHub API cache"""
    global _GITHUB_API_CACHE, _GITHUB_API_LOCK
    with _GITHUB_API_LOCK:
        return {
            "cache_size": len(_GITHUB_API_CACHE),
            "cached_repos": list(set(f"{k.split(':')[0]}/{k.split(':')[1]}" for k in _GITHUB_API_CACHE.keys())),
        }
