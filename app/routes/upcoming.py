"""
Upcoming Games Routes - Endpoints para visualizar futuros lançamentos
"""
import os
import json
import time
import logging
from datetime import datetime
from flask import Blueprint, jsonify
from app_services.rating_service import IGDBClient
from settings import load_settings
from auth import access_required

logger = logging.getLogger("main")
upcoming_bp = Blueprint("upcoming", __name__, url_prefix="/api")

CACHE_FILE = "upcoming_cache.json"
CACHE_TTL = 86400  # 24 hours

def get_cached_upcoming():
    """Retrieve upcoming games from cache if valid"""
    if not os.path.exists(CACHE_FILE):
        return None
    
    try:
        with open(CACHE_FILE, 'r') as f:
            cache_data = json.load(f)
            
        if time.time() - cache_data.get("timestamp", 0) < CACHE_TTL:
            return cache_data.get("games")
    except Exception as e:
        logger.error(f"Error reading upcoming cache: {e}")
        
    return None

def save_upcoming_cache(games):
    """Save upcoming games to cache"""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump({
                "timestamp": time.time(),
                "games": games
            }, f)
    except Exception as e:
        logger.error(f"Error saving upcoming cache: {e}")

@upcoming_bp.route("/upcoming")
@access_required("shop")
def get_upcoming():
    """Fetch and return upcoming Nintendo Switch games"""
    # 1. Try cache
    cached_games = get_cached_upcoming()
    if cached_games:
        return jsonify({"games": cached_games, "source": "cache"})
    
    # 2. Fetch from IGDB
    settings = load_settings()
    igdb_id = settings.get("apis", {}).get("igdb_client_id")
    igdb_secret = settings.get("apis", {}).get("igdb_client_secret")
    
    if not igdb_id or not igdb_secret:
        return jsonify({
            "error": "IGDB API not configured", 
            "message": "Configure o Client ID e Client Secret do IGDB nas Configurações para ver os próximos lançamentos."
        }), 400
        
    try:
        igdb = IGDBClient(igdb_id, igdb_secret)
        games = igdb.get_upcoming_games(limit=50)
        
        # Normalize/Format data if needed
        for game in games:
            if "first_release_date" in game:
                game["release_date_formatted"] = datetime.fromtimestamp(game["first_release_date"]).strftime('%d/%m/%Y')
            
            if "cover" in game and "url" in game["cover"]:
                # Upgrade cover resolution
                game["cover_url"] = "https:" + game["cover"]["url"].replace("t_thumb", "t_cover_big")
            else:
                game["cover_url"] = "/static/img/no-icon.png"
                
        save_upcoming_cache(games)
        return jsonify({"games": games, "source": "api"})
        
    except Exception as e:
        logger.error(f"IGDB API failed to fetch upcoming: {e}")
        return jsonify({"error": str(e)}), 500
