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


class IGDBClient:
    """Client for IGDB API (via Twitch)"""
    
    _access_token = None
    _token_expiry = 0
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://api.igdb.com/v4"
        self.session = requests.Session()
    
    def _get_access_token(self):
        """Get or refresh OAuth2 access token"""
        now = time.time()
        if IGDBClient._access_token and IGDBClient._token_expiry > now + 60:
            return IGDBClient._access_token
            
        try:
            auth_url = f"https://id.twitch.tv/oauth2/token"
            params = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials"
            }
            response = requests.post(auth_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            IGDBClient._access_token = data["access_token"]
            IGDBClient._token_expiry = now + data["expires_in"]
            return IGDBClient._access_token
        except Exception as e:
            logger.error(f"IGDB auth failed: {e}")
            raise RatingAPIException(f"IGDB Auth failed: {e}")

    def search_game(self, title: str) -> Optional[Dict]:
        """Search for a game and return best match with rating/screenshots"""
        token = self._get_access_token()
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {token}"
        }
        
        # Query for Switch games with specific fields
        # platform 130 = Nintendo Switch
        query = f'search "{title}"; fields name, aggregated_rating, rating, total_rating_count, genres.name, screenshots.url, platforms; where platforms = (130); limit 5;'
        
        try:
            response = self.session.post(
                f"{self.base_url}/games",
                headers=headers,
                data=query,
                timeout=10
            )
            response.raise_for_status()
            results = response.json()
            
            if not results:
                # Try search without platform filter (sometimes they don't have switch platform correctly tagged)
                query_fallback = f'search "{title}"; fields name, aggregated_rating, rating, total_rating_count, genres.name, screenshots.url; limit 5;'
                response = self.session.post(
                    f"{self.base_url}/games",
                    headers=headers,
                    data=query_fallback,
                    timeout=10
                )
                results = response.json()
                
            if not results:
                return None
            
            # Return best match
            return results[0]
        except Exception as e:
            logger.error(f"IGDB search error for '{title}': {e}")
            raise RatingAPIException(f"IGDB search failed: {e}")


def fetch_game_metadata(title_name: str, title_id: str = None) -> Optional[Dict[str, Any]]:
    """
    Main function to fetch game metadata from APIs
    Returns normalized data structure targeting RAWG and IGDB
    """
    from settings import load_settings
    settings = load_settings()
    
    rawg_key = settings.get("apis", {}).get("rawg_api_key")
    igdb_id = settings.get("apis", {}).get("igdb_client_id")
    igdb_secret = settings.get("apis", {}).get("igdb_client_secret")
    
    metadata = {}
    
    # 1. Try RAWG first (Better screenshots/playtime)
    if rawg_key:
        try:
            rawg = RAWGClient(rawg_key)
            search = rawg.search_game(title_name)
            if search:
                details = rawg.get_game_details(search["id"])
                metadata = {
                    "metacritic_score": details.get("metacritic") or metadata.get("metacritic_score"),
                    "rawg_rating": details.get("rating"),
                    "rating_count": details.get("ratings_count"),
                    "playtime_main": details.get("playtime"),
                    "genres": [g["name"] for g in details.get("genres", [])],
                    "tags": [t["name"] for t in details.get("tags", [])[:10]],
                    "screenshots": [
                        {"url": s["image"], "source": "rawg"}
                        for s in details.get("short_screenshots", [])[:5]
                    ],
                    "api_source": "rawg",
                    "api_last_update": datetime.now()
                }
        except Exception as e:
            logger.warning(f"RAWG fail for {title_name}: {e}")

    # 2. Try IGDB (Better ratings accuracy/names)
    if igdb_id and igdb_secret:
        try:
            igdb = IGDBClient(igdb_id, igdb_secret)
            res = igdb.search_game(title_name)
            if res:
                # Merge or Fill missing data
                if not metadata.get("metacritic_score") and res.get("aggregated_rating"):
                    metadata["metacritic_score"] = int(res["aggregated_rating"])
                
                if not metadata.get("rawg_rating") and res.get("rating"):
                    metadata["rawg_rating"] = res["rating"] / 20.0 # Convert 0-100 to 0-5
                
                if not metadata.get("genres") and res.get("genres"):
                    metadata["genres"] = [g["name"] for g in res["genres"]]
                
                if not metadata.get("screenshots") and res.get("screenshots"):
                    igdb_screens = [
                        {"url": f"https:{s['url'].replace('t_thumb', 't_720p')}", "source": "igdb"}
                        for s in res["screenshots"][:5]
                    ]
                    if not metadata.get("screenshots"):
                        metadata["screenshots"] = igdb_screens
                    else:
                        # Append up to total 10
                        metadata["screenshots"].extend(igdb_screens)
                        metadata["screenshots"] = metadata["screenshots"][:10]
                
                if not metadata.get("api_source"):
                    metadata["api_source"] = "igdb"
                
                metadata["api_last_update"] = datetime.now()
        except Exception as e:
            logger.warning(f"IGDB fail for {title_name}: {e}")

    return metadata if metadata else None


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
