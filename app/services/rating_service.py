"""
Service layer for fetching game ratings and metadata from external APIs
"""
import requests
import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger("main")

# API Configuration
RAWG_BASE_URL = "https://api.rawg.io/api"
CACHE_TTL_DAYS = 30  # Cache API results for 30 days

class RatingAPIException(Exception):
    """Base exception for rating API errors"""
    pass

class RAWGClient:
    """Client for RAWG API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MyFoil Nintendo Switch Library Manager"
        })
        self.last_request_time = 0
        self.rate_limit_delay = 0.5  # 2 requests per second
    
    def _rate_limit(self):
        """Ensure we don't exceed rate limits"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()
    
    def search_game(self, title: str, platform: str = "nintendo-switch") -> Optional[Dict]:
        """Search for a game by title"""
        if not self.api_key:
            return None
            
        self._rate_limit()
        
        try:
            params = {
                "key": self.api_key,
                "search": title,
                "platforms": "7",  # 7 = Nintendo Switch ID
                "page_size": 5
            }
            
            response = self.session.get(
                f"{RAWG_BASE_URL}/games",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                logger.warning(f"No RAWG results for '{title}'")
                return None
            
            # Return best match (first result)
            return results[0]
            
        except requests.RequestException as e:
            logger.error(f"RAWG API error for '{title}': {e}")
            raise RatingAPIException(f"RAWG API failed: {e}")
    
    def get_game_details(self, rawg_id: int) -> Dict[str, Any]:
        """Get detailed game information by RAWG ID"""
        if not self.api_key:
            return {}
            
        self._rate_limit()
        
        try:
            response = self.session.get(
                f"{RAWG_BASE_URL}/games/{rawg_id}",
                params={"key": self.api_key},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            logger.error(f"RAWG details error for ID {rawg_id}: {e}")
            raise RatingAPIException(f"RAWG details failed: {e}")


def fetch_game_metadata(title_name: str, title_id: str = None) -> Optional[Dict[str, Any]]:
    """
    Main function to fetch game metadata from APIs
    Returns normalized data structure
    """
    from settings import load_settings
    
    settings = load_settings()
    # Assuming apis section exists or returning None if not
    api_key = settings.get("apis", {}).get("rawg_api_key")
    
    if not api_key:
        logger.warning("RAWG API key not configured, skipping metadata fetch")
        return None
    
    try:
        client = RAWGClient(api_key)
        
        # Search for the game
        search_result = client.search_game(title_name)
        if not search_result:
            return None
        
        rawg_id = search_result.get("id")
        
        # Get full details
        details = client.get_game_details(rawg_id)
        
        # Normalize data
        metadata = {
            "rawg_id": rawg_id,
            "metacritic_score": details.get("metacritic"),
            "rawg_rating": details.get("rating"),  # 0-5
            "rating_count": details.get("ratings_count"),
            "playtime_main": details.get("playtime"),  # Average hours
            "genres": [g["name"] for g in details.get("genres", [])],
            "tags": [t["name"] for t in details.get("tags", [])[:10]],  # Top 10 tags
            "screenshots": [
                {"url": s["image"], "source": "rawg"}
                for s in details.get("short_screenshots", [])[:5]
            ],
            "api_source": "rawg",
            "api_last_update": datetime.now()
        }
        
        logger.info(f"Fetched metadata for '{title_name}' (RAWG ID: {rawg_id})")
        return metadata
        
    except Exception as e:
        logger.error(f"Error fetching metadata for '{title_name}': {e}")
        return None


def should_update_metadata(game_obj) -> bool:
    """Check if metadata should be refreshed"""
    if not game_obj.api_last_update:
        return True
    
    # Handle if api_last_update is a string (SQLite issues sometimes)
    actual_last_update = game_obj.api_last_update
    if isinstance(actual_last_update, str):
        try:
            actual_last_update = datetime.fromisoformat(actual_last_update)
        except ValueError:
            return True

    age = datetime.now() - actual_last_update
    return age > timedelta(days=CACHE_TTL_DAYS)


def update_game_metadata(game_obj, force: bool = False):
    """Update a game object with fresh metadata from APIs"""
    from db import db
    
    if not force and not should_update_metadata(game_obj):
        logger.debug(f"Metadata for {game_obj.name} is fresh, skipping")
        return False
    
    metadata = fetch_game_metadata(game_obj.name, game_obj.title_id)
    if not metadata:
        return False
    
    # Update fields
    game_obj.rawg_id = metadata.get("rawg_id")
    game_obj.metacritic_score = metadata.get("metacritic_score")
    game_obj.rawg_rating = metadata.get("rawg_rating")
    game_obj.rating_count = metadata.get("rating_count")
    game_obj.playtime_main = metadata.get("playtime_main")
    game_obj.genres_json = metadata.get("genres")
    game_obj.tags_json = metadata.get("tags")
    game_obj.screenshots_json = metadata.get("screenshots")
    game_obj.api_source = metadata.get("api_source")
    game_obj.api_last_update = metadata.get("api_last_update")
    
    db.session.commit()
    logger.info(f"Updated metadata for {game_obj.name}")
    return True
