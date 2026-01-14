"""
TitleDB Source Manager for MyFoil
Supports multiple sources with automatic fallback and configurable priorities
"""
import requests
import os
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger('main')

class TitleDBSource:
    """Represents a single TitleDB source"""
    
    def __init__(self, name: str, base_url: str, enabled: bool = True, priority: int = 0, source_type: str = 'json'):
        self.name = name
        self.base_url = base_url.rstrip('/')
        self.enabled = enabled
        self.priority = priority
        self.source_type = source_type # 'json' or 'zip_legacy'
        self.last_success = None
        self.last_error = None
        self.remote_date = None
        self.is_fetching = False
        
    def get_file_url(self, filename: str) -> str:
        """Get the full URL for a specific file"""
        return f"{self.base_url}/{filename}"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'name': self.name,
            'base_url': self.base_url,
            'enabled': self.enabled,
            'priority': self.priority,
            'source_type': self.source_type,
            'last_success': self.last_success.isoformat() if self.last_success else None,
            'last_error': self.last_error,
            'remote_date': self.remote_date.isoformat() if self.remote_date else None,
            'is_fetching': self.is_fetching
        }

    def get_last_modified_date(self, filename: str) -> Optional[datetime]:
        """Get the last modified date of the specific file from the source"""
        url = self.get_file_url(filename)
        try:
            # Check if it's a raw GitHub URL
            if "raw.githubusercontent.com" in self.base_url:
                # GitHub raw URLs update immediately, but don't always expose Last-Modified
                # For more accuracy, one would hit the API, but HEAD is cheap.
                # Let's try to get info from the repo API if possible.
                # Convention: https://raw.githubusercontent.com/<user>/<repo>/<branch>
                parts = self.base_url.split('/')
                if len(parts) >= 6:
                    user = parts[3]
                    repo = parts[4]
                    branch = parts[5]
                    # Use GitHub API to get commit info for the file
                    api_url = f"https://api.github.com/repos/{user}/{repo}/commits?path={filename}&sha={branch}&per_page=1"
                    
                    # GitHub API requires a User-Agent
                    headers = {
                        'User-Agent': 'MyFoil-App',
                        'Accept': 'application/vnd.github.v3+json'
                    }
                    
                    resp = requests.get(api_url, headers=headers, timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data and isinstance(data, list) and len(data) > 0:
                            commit_date = data[0]['commit']['committer']['date']
                            # Remove 'Z' if present for ISO parsing compatibility
                            return datetime.fromisoformat(commit_date.replace("Z", "+00:00"))
                        elif isinstance(data, dict) and data.get('message'):
                            logger.error(f"GitHub API Error for {self.name}: {data['message']}")
                    else:
                        logger.error(f"GitHub API returned {resp.status_code} for {self.name}: {resp.text}")
            
            # Fallback to standard HEAD request
            response = requests.head(url, timeout=5)
            if response.status_code == 200:
                if 'Last-Modified' in response.headers:
                    # Parse RFC 2822 date
                    return datetime.strptime(response.headers['Last-Modified'], '%a, %d %b %Y %H:%M:%S %Z')
        except Exception as e:
            logger.error(f"Error fetching remote date for {self.name} ({url}): {e}")
        
        return None
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TitleDBSource':
        """Create from dictionary"""
        source = cls(
            name=data['name'],
            base_url=data['base_url'],
            enabled=data.get('enabled', True),
            priority=data.get('priority', 0),
            source_type=data.get('source_type', 'json')
        )
        if data.get('last_success'):
            source.last_success = datetime.fromisoformat(data['last_success'])
        if data.get('remote_date'):
            source.remote_date = datetime.fromisoformat(data['remote_date'])
        source.last_error = data.get('last_error')
        return source


class TitleDBSourceManager:
    """Manages multiple TitleDB sources with fallback support"""
    
    # Default sources
    DEFAULT_SOURCES = [
        TitleDBSource(
            name="tinfoil.media",
            base_url="https://tinfoil.media/repo/db",
            priority=1,
            source_type='json'
        ),
        TitleDBSource(
            name="MyFoil (Legacy)",
            base_url="https://nightly.link/a1ex4/ownfoil/workflows/region_titles/master/titledb.zip",
            enabled=True,
            priority=2,
            source_type='zip_legacy'
        ),
        TitleDBSource(
            name="blawar/titledb (GitHub)",
            base_url="https://raw.githubusercontent.com/blawar/titledb/master",
            priority=3,
            source_type='json'
        ),
        TitleDBSource(
            name="julesontheroad/titledb (GitHub)",
            base_url="https://raw.githubusercontent.com/julesontheroad/titledb/master",
            priority=4,
            source_type='json'
        )
    ]
    
    def __init__(self, config_dir: str):
        self.config_dir = Path(config_dir)
        self.sources_file = self.config_dir / 'titledb_sources.json'
        self.sources: List[TitleDBSource] = []
        self.load_sources()
    
    def load_sources(self):
        """Load sources from config file or use defaults"""
        if self.sources_file.exists():
            try:
                with open(self.sources_file, 'r') as f:
                    data = json.load(f)
                    self.sources = [TitleDBSource.from_dict(s) for s in data]
                logger.info(f"Loaded {len(self.sources)} TitleDB sources from config")
            except Exception as e:
                logger.error(f"Error loading TitleDB sources: {e}, using defaults")
                self.sources = self.DEFAULT_SOURCES.copy()
        else:
            logger.info("No TitleDB sources config found, using defaults")
            self.sources = self.DEFAULT_SOURCES.copy()
            self.save_sources()
    
    def save_sources(self):
        """Save sources to config file"""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.sources_file, 'w') as f:
                json.dump([s.to_dict() for s in self.sources], f, indent=2)
            logger.debug("Saved TitleDB sources to config")
        except Exception as e:
            logger.error(f"Error saving TitleDB sources: {e}")
    
    def get_active_sources(self) -> List[TitleDBSource]:
        """Get enabled sources sorted by priority"""
        active = [s for s in self.sources if s.enabled]
        return sorted(active, key=lambda x: x.priority)
    
    def download_file(self, filename: str, dest_path: str, timeout: int = 30) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Download a file from sources with automatic fallback
        
        Returns:
            Tuple of (success, source_name, error_message)
        """
        active_sources = self.get_active_sources()
        
        if not active_sources:
            return False, None, "No active TitleDB sources configured"
        
        for source in active_sources:
            url = source.get_file_url(filename)
            logger.info(f"Attempting to download {filename} from {source.name}...")
            
            try:
                response = requests.get(url, timeout=timeout, stream=True)
                response.raise_for_status()
                
                # Write to file
                with open(dest_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Update source status
                source.last_success = datetime.now()
                source.last_error = None
                self.save_sources()
                
                logger.info(f"Successfully downloaded {filename} from {source.name}")
                return True, source.name, None
                
            except requests.exceptions.RequestException as e:
                error_msg = f"Failed to download from {source.name}: {str(e)}"
                logger.warning(error_msg)
                source.last_error = str(e)
                continue
            except Exception as e:
                error_msg = f"Unexpected error with {source.name}: {str(e)}"
                logger.error(error_msg)
                source.last_error = str(e)
                continue
        
        # All sources failed
        self.save_sources()
        return False, None, "All TitleDB sources failed"
    
    def add_source(self, name: str, base_url: str, priority: int = 50, enabled: bool = True, source_type: str = 'json') -> bool:
        """Add a new custom source"""
        # Check if source already exists
        if any(s.name == name for s in self.sources):
            logger.warning(f"Source {name} already exists")
            return False
        
        new_source = TitleDBSource(name, base_url, enabled, priority, source_type)
        self.sources.append(new_source)
        self.save_sources()
        logger.info(f"Added new TitleDB source: {name} (Type: {source_type})")
        return True
    
    def remove_source(self, name: str) -> bool:
        """Remove a source by name"""
        original_count = len(self.sources)
        self.sources = [s for s in self.sources if s.name != name]
        
        if len(self.sources) < original_count:
            self.save_sources()
            logger.info(f"Removed TitleDB source: {name}")
            return True
        
        logger.warning(f"Source {name} not found")
        return False
    
    def update_source(self, name: str, **kwargs) -> bool:
        """Update source properties"""
        for source in self.sources:
            if source.name == name:
                if 'base_url' in kwargs:
                    source.base_url = kwargs['base_url'].rstrip('/')
                if 'enabled' in kwargs:
                    source.enabled = kwargs['enabled']
                if 'priority' in kwargs:
                    source.priority = kwargs['priority']
                
                self.save_sources()
                logger.info(f"Updated TitleDB source: {name}")
                return True
        
        logger.warning(f"Source {name} not found")
        return False
    
    def get_sources_status(self) -> List[Dict]:
        """Get status of all sources using cached dates"""
        return [s.to_dict() for s in sorted(self.sources, key=lambda x: x.priority)]

    def refresh_remote_dates(self):
        """Asynchronously refresh remote dates for all enabled sources"""
        import threading
        thread = threading.Thread(target=self._refresh_remote_dates_worker)
        thread.daemon = True
        thread.start()

    def _refresh_remote_dates_worker(self):
        """Worker thread for remote date refreshing"""
        from settings import load_settings
        import titledb
        
        logger.info("Starting background TitleDB remote date refresh...")
        app_settings = load_settings()
        ref_file = titledb.get_region_titles_file(app_settings) or "titles.json"
        
        for source in self.sources:
            if not source.enabled:
                continue
                
            source.is_fetching = True
            try:
                new_date = source.get_last_modified_date(ref_file)
                if new_date:
                    source.remote_date = new_date
            finally:
                source.is_fetching = False
        
        self.save_sources()
        logger.info("Finished background TitleDB remote date refresh.")

    def update_priorities(self, priority_map: Dict[str, int]) -> bool:
        """
        Batch update priorities.
        priority_map: { 'source_name': new_priority_int }
        """
        changed = False
        for source in self.sources:
            if source.name in priority_map:
                new_prio = priority_map[source.name]
                if source.priority != new_prio:
                    source.priority = new_prio
                    changed = True
        
        if changed:
            self.save_sources()
            logger.info("Batch updated TitleDB source priorities")
        return True
