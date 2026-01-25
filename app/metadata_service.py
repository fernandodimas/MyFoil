import requests
import logging
from datetime import datetime
from typing import Dict, Optional, Any
from db import db, TitleMetadata, MetadataFetchLog, Titles
from job_tracker import job_tracker
import os
import time

logger = logging.getLogger(__name__)

class MetadataFetcher:
    """Service to fetch metadata from remote sources (RAWG, IGDB, Nintendo)"""
    
    def __init__(self):
        self.rawg_api_key = os.environ.get('RAWG_API_KEY', '')
        # Future: IGDB and other sources
    
    def should_fetch_metadata(self) -> bool:
        """Decide if it's time to run the scheduled fetch (every 12h)"""
        last_fetch = MetadataFetchLog.query.filter_by(
            status='completed'
        ).order_by(MetadataFetchLog.completed_at.desc()).first()
        
        if not last_fetch:
            logger.info("First time metadata fetch - should run")
            return True
        
        # passed 12 hours?
        hours_since_last = (datetime.now() - last_fetch.completed_at).total_seconds() / 3600
        
        if hours_since_last >= 12:
            logger.info(f"Last fetch was {hours_since_last:.1f}h ago - should run")
            return True
        
        logger.debug(f"Last fetch was {hours_since_last:.1f}h ago - will skip")
        return False
    
    def fetch_all_metadata(self, force: bool = False):
        """Fetch metadata for all titles in the library"""
        
        if not force and not self.should_fetch_metadata():
            logger.info("Skipping metadata fetch (within 12h window)")
            return
        
        # Create log entry
        fetch_log = MetadataFetchLog(
            started_at=datetime.now(),
            status='running'
        )
        db.session.add(fetch_log)
        db.session.commit()
        
        # Register job in tracker
        job_id = job_tracker.register_job('metadata_fetch_all', {
            'fetch_log_id': fetch_log.id
        })
        job_tracker.start_job(job_id)
        
        try:
            # Fetch only for games we actually HAVE in library (have_base=True)
            titles = Titles.query.filter_by(have_base=True).all()
            total = len(titles)
            
            logger.info(f"Starting metadata fetch for {total} library titles")
            
            processed = 0
            updated = 0
            failed = 0
            
            for i, title in enumerate(titles):
                try:
                    job_tracker.update_progress(job_id, i+1, total, 
                        f"Fetching metadata for {title.name or title.title_id}...")
                    
                    sources_results = self.fetch_for_title(title)
                    
                    if len(sources_results) > 0:
                        updated += 1
                    
                    processed += 1
                    
                    # Periodic commit to avoid large transaction
                    if processed % 10 == 0:
                        db.session.commit()
                        logger.debug(f"Progress: {processed}/{total} titles processed")
                        
                    # Respect API limits (simple delay)
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Error fetching metadata for {title.title_id}: {e}")
                    failed += 1
            
            db.session.commit()
            
            # Update execution log
            fetch_log.completed_at = datetime.now()
            fetch_log.status = 'completed'
            fetch_log.titles_processed = processed
            fetch_log.titles_updated = updated
            fetch_log.titles_failed = failed
            db.session.commit()
            
            logger.info(f"Metadata fetch complete: {processed} titles processed, {updated} updated, {failed} failed")
            
            job_tracker.complete_job(job_id, {
                'processed': processed,
                'updated': updated,
                'failed': failed
            })
            
        except Exception as e:
            logger.error(f"Fatal metadata fetch error: {e}")
            fetch_log.status = 'failed'
            fetch_log.error_message = str(e)
            fetch_log.completed_at = datetime.now()
            db.session.commit()
            
            job_tracker.fail_job(job_id, str(e))
    
    def fetch_for_title(self, title: Titles) -> Dict[str, Any]:
        """Fetch metadata for a single title from all sources"""
        results = {}
        
        # Source 1: RAWG
        if self.rawg_api_key:
            try:
                # Use name if available, otherwise title_id (not ideal for search)
                search_term = title.name or title.title_id
                data = self._fetch_from_rawg(search_term)
                if data:
                    self._save_metadata(title.title_id, 'rawg', data)
                    results['rawg'] = data
            except Exception as e:
                logger.warning(f"RAWG fetch failed for {title.title_id}: {e}")
        
        return results
    
    def _fetch_from_rawg(self, game_name: str) -> Optional[Dict]:
        """Search and fetch from RAWG.io API"""
        if not self.rawg_api_key or not game_name:
            return None
            
        url = "https://api.rawg.io/api/games"
        params = {
            'key': self.rawg_api_key,
            'search': game_name,
            'page_size': 1,
            'platforms': '7' # Nintendo Switch
        }
        
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            if not data.get('results'):
                return None
            
            game = data['results'][0]
            
            # Convert released string to date object
            rel_date = None
            if game.get('released'):
                try:
                    rel_date = datetime.strptime(game['released'], '%Y-%m-%d').date()
                except:
                    pass

            return {
                'description': game.get('description_raw', ''),
                'rating': game.get('rating', 0) * 20, # Normalizing 0-5 to 0-100
                'rating_count': game.get('ratings_count', 0),
                'genres': [g['name'] for g in game.get('genres', [])],
                'tags': [t['name'] for t in game.get('tags', [])[:10]],
                'release_date': rel_date,
                'cover_url': game.get('background_image'),
                'screenshots': [s['image'] for s in game.get('short_screenshots', [])[:5]],
                'source_id': str(game.get('id'))
            }
        except Exception as e:
            logger.debug(f"RAWG API error: {e}")
            return None
            
    def _save_metadata(self, title_id: str, source: str, data: Dict):
        """Persist metadata to DB, handling updates"""
        existing = TitleMetadata.query.filter_by(
            title_id=title_id,
            source=source
        ).first()
        
        if existing:
            # Update existing
            for key, value in data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.updated_at = datetime.now()
        else:
            # Create new
            metadata = TitleMetadata(
                title_id=title_id,
                source=source,
                **data
            )
            db.session.add(metadata)

# Singleton instance
metadata_fetcher = MetadataFetcher()
