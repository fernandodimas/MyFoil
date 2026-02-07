"""
TitleDB Source Manager for MyFoil
Supports multiple sources with automatic fallback and configurable priorities
"""

import requests
import json
import os
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from pathlib import Path
from utils import format_datetime, ensure_utc, now_utc

logger = logging.getLogger("main")


class TitleDBSource:
    """Represents a single TitleDB source"""

    def __init__(self, name: str, base_url: str, enabled: bool = True, priority: int = 0, source_type: str = "json"):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.enabled = enabled
        self.priority = priority
        self.source_type = source_type  # 'json' or 'zip_legacy'
        self.last_success = None
        self.last_error = None
        self.remote_date = None
        self.is_fetching = False

    def get_file_url(self, filename: str) -> str:
        """Get the full URL for a specific file"""
        return f"{self.base_url}/{filename}"

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization (formatted for UI)"""
        return {
            "name": self.name,
            "base_url": self.base_url,
            "enabled": self.enabled,
            "priority": self.priority,
            "source_type": self.source_type,
            "last_success": format_datetime(self.last_success) if self.last_success else None,
            "last_error": self.last_error,
            "remote_date": format_datetime(self.remote_date) if self.remote_date else None,
            "is_fetching": self.is_fetching,
        }

    def to_dict_raw(self) -> Dict:
        """Convert to dictionary for persistent storage (ISO UTC)"""
        return {
            "name": self.name,
            "base_url": self.base_url,
            "enabled": self.enabled,
            "priority": self.priority,
            "source_type": self.source_type,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_error": self.last_error,
            "remote_date": self.remote_date.isoformat() if self.remote_date else None,
            "is_fetching": self.is_fetching,
        }

    def get_last_modified_date(self, filenames: List[str]) -> Optional[datetime]:
        """Get the last modified date of any of the regional files from the source"""
        if not isinstance(filenames, list):
            filenames = [filenames]

        try:
            # Check if it's a raw GitHub URL
            if "raw.githubusercontent.com" in self.base_url:
                # https://raw.githubusercontent.com/<user>/<repo>/<branch>
                # OR https://raw.githubusercontent.com/<user>/<repo>/refs/heads/<branch>
                parts = self.base_url.split("/")
                if len(parts) >= 6:
                    user = parts[3]
                    repo = parts[4]
                    
                    # Detect new GitHub URL format: .../<user>/<repo>/refs/heads/<branch>
                    if parts[5] == "refs" and len(parts) >= 8 and parts[6] == "heads":
                        branch = parts[7].rstrip("/")
                    else:
                        branch = parts[5].rstrip("/")

                    # Keep track if we hit rate limits to stop trying files/branches immediately
                    self._rate_limit_hit = False

                    # Import the caching function
                    try:
                        from github_api_cache import get_github_date_cached

                        use_cache = True
                    except ImportError:
                        use_cache = False
                        logger.debug("GitHub API cache not available, using direct requests")

                    # Try to get commit info for the file
                    def _get_github_date(fname, br):
                        if getattr(self, "_rate_limit_hit", False):
                            return None

                        api_url = f"https://api.github.com/repos/{user}/{repo}/commits?path={fname}&sha={br}&per_page=1"
                        headers = {"User-Agent": "MyFoil-App", "Accept": "application/vnd.github.v3+json"}

                        # Use cached version if available
                        if use_cache:
                            return get_github_date_cached(api_url, headers)

                        # Fallback to direct request
                        try:
                            resp = requests.get(api_url, headers=headers, timeout=5)
                            if resp.status_code == 200:
                                data = resp.json()
                                if data and isinstance(data, list) and len(data) > 0:
                                    commit_date = data[0]["commit"]["committer"]["date"]
                                    return datetime.fromisoformat(commit_date.replace("Z", "+00:00"))
                            elif resp.status_code == 403:
                                if not getattr(self, "_rate_limit_hit", False):
                                    logger.warning(
                                        f"GitHub API rate limited for {self.name} - aborting further checks."
                                    )
                                    self._rate_limit_hit = True
                                return None
                        except Exception as e:
                            logger.debug(f"GitHub API error for {fname} on {br}: {e}")
                        return None

                    # Try each filename on the branch
                    for fname in filenames:
                        d = _get_github_date(fname, branch)
                        if d:
                            return d
                        if getattr(self, "_rate_limit_hit", False):
                            return None

                    # Try generic titles.json
                    if "titles.json" not in filenames:
                        d = _get_github_date("titles.json", branch)
                        if d:
                            return d
                        if getattr(self, "_rate_limit_hit", False):
                            return None

                    # Fallback branch check
                    alt_branch = "master" if branch == "main" else "main"
                    for fname in filenames:
                        d = _get_github_date(fname, alt_branch)
                        if d:
                            return d
                        if getattr(self, "_rate_limit_hit", False):
                            return None

            # Fallback to standard HEAD request for each filename
            for fname in filenames:
                url = self.get_file_url(fname)
                try:
                    response = requests.head(url, timeout=5)
                    if response.status_code == 200:
                        if "Last-Modified" in response.headers:
                            return datetime.strptime(response.headers["Last-Modified"], "%a, %d %b %Y %H:%M:%S %Z")
                except:
                    pass

            # Final attempt: try generic titles.json
            if "titles.json" not in filenames:
                url_generic = self.get_file_url("titles.json")
                try:
                    response = requests.head(url_generic, timeout=5)
                    if response.status_code == 200 and "Last-Modified" in response.headers:
                        return datetime.strptime(response.headers["Last-Modified"], "%a, %d %b %Y %H:%M:%S %Z")
                except:
                    pass

        except Exception as e:
            logger.debug(f"Error fetching remote date for {self.name}: {e}")

        return None

    @classmethod
    def from_dict(cls, data: Dict) -> "TitleDBSource":
        """Create from dictionary"""
        source = cls(
            name=data["name"],
            base_url=data["base_url"],
            enabled=data.get("enabled", True),
            priority=data.get("priority", 0),
            source_type=data.get("source_type", "json"),
        )
        if data.get("last_success"):
            source.last_success = ensure_utc(datetime.fromisoformat(data["last_success"]))
        
        if data.get("remote_date"):
            source.remote_date = ensure_utc(datetime.fromisoformat(data["remote_date"]))
        source.last_error = data.get("last_error")
        return source


class TitleDBSourceManager:
    """Manages multiple TitleDB sources with fallback support"""

    # Default sources
    DEFAULT_SOURCES = [
        TitleDBSource(
            name="blawar/titledb (GitHub)",
            base_url="https://raw.githubusercontent.com/blawar/titledb/refs/heads/master",
            priority=10,
            source_type="json",
        ),
        TitleDBSource(name="tinfoil.media", base_url="https://tinfoil.media/repo/db", priority=1, source_type="json"),
        TitleDBSource(
            name="MyFoil (Legacy)",
            base_url="https://nightly.link/a1ex4/ownfoil/workflows/region_titles/master/titledb.zip",
            enabled=True,
            priority=5,
            source_type="zip_legacy",
        ),
    ]

    def __init__(self, config_dir: str):
        self.config_dir = Path(config_dir)
        self.sources_file = self.config_dir / "titledb_sources.json"
        self.sources: List[TitleDBSource] = []
        self.last_refresh_time = 0 # timestamp
        self.load_sources()

    def load_sources(self):
        """Load sources from config file or use defaults"""
        if self.sources_file.exists():
            try:
                with open(self.sources_file, "r") as f:
                    data = json.load(f)
                    self.sources = [TitleDBSource.from_dict(s) for s in data]

                # Migration: Remove defunct sources and add new defaults
                [s.base_url for s in self.sources]
                defunct_urls = [
                    "https://raw.githubusercontent.com/Big-On-The-Bottle/titledb/main",
                    "https://raw.githubusercontent.com/julesontheroad/titledb/master",
                ]
                defunct_names = ["bottle/titledb (GitHub)", "julesontheroad/titledb (GitHub)"]

                # Filter out defunct
                original_count = len(self.sources)
                self.sources = [
                    s for s in self.sources if s.base_url not in defunct_urls and s.name not in defunct_names
                ]

                # Add missing defaults
                added = False
                new_config_urls = [s.base_url for s in self.sources]
                for default_s in self.DEFAULT_SOURCES:
                    if default_s.base_url not in new_config_urls:
                        self.sources.append(default_s)
                        added = True

                if len(self.sources) != original_count or added:
                    logger.info("Syncing TitleDB sources (removing defunct or adding newly defaults)...")
                    self.save_sources()

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
            with open(self.sources_file, "w") as f:
                json.dump([s.to_dict_raw() for s in self.sources], f, indent=2)
            logger.debug("Saved TitleDB sources to config")
        except Exception as e:
            logger.error(f"Error saving TitleDB sources: {e}")

    def get_active_sources(self) -> List[TitleDBSource]:
        """Get enabled sources sorted by priority (asc) or by most recent remote date (desc)"""
        active = [s for s in self.sources if s.enabled]
        
        # Load settings to check auto_use_latest
        try:
            from settings import load_settings
            app_settings = load_settings()
            auto_use_latest = app_settings.get("titles", {}).get("auto_use_latest", False)
        except:
            auto_use_latest = False
            
        def sort_key(s):
            # Freshness: Newer is better (larger timestamp)
            if s.remote_date:
                try:
                    remote_ts = ensure_utc(s.remote_date).timestamp()
                except:
                    remote_ts = 0
            else:
                remote_ts = 0
                
            # Priority: Lower is better (0 comes before 1)
            prio = s.priority
            
            if auto_use_latest and remote_ts > 0:
                # If auto-use latest is ON, freshness comes FIRST
                return (-remote_ts, prio)
            else:
                # Default: Priority comes FIRST
                return (prio, -remote_ts)

        return sorted(active, key=sort_key)

    def download_file(
        self, filename: str, dest_path: str, timeout: int = 30, silent_404: bool = False
    ) -> Tuple[bool, Optional[str], Optional[str]]:
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
                # Write to temp file to ensure atomicity
                tmp_path = dest_path + ".tmp"
                with open(tmp_path, "wb") as f:
                    # Peek first chunk for validation
                    first_chunk = True
                    for chunk in response.iter_content(chunk_size=8192):
                        if first_chunk:
                            # Basic validation: Check if it looks like an HTML error page instead of JSON/File
                            if chunk.lstrip().startswith(b"<!DOCTYPE html") or chunk.lstrip().startswith(b"<html"):
                                logger.warning(f"Source {source.name} returned HTML instead of expected file. Skipping.")
                                raise Exception("Invalid content: Received HTML")
                            first_chunk = False
                        f.write(chunk)

                # Rename to final destination (Atomic operation)
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                os.rename(tmp_path, dest_path)

                # Update source status
                source.last_success = datetime.now(timezone.utc)
                source.last_error = None
                self.save_sources()

                logger.info(f"Successfully downloaded {filename} from {source.name}")
                return True, source.name, None

            except requests.exceptions.RequestException as e:
                error_str = str(e)
                error_msg = f"Failed to download from {source.name}: {error_str}"
                
                if silent_404 and ("404" in error_str or "not found" in error_str.lower()):
                    logger.debug(f"{filename} not found on {source.name} (skipping silently)")
                else:
                    logger.warning(error_msg)
                
                source.last_error = error_str
                continue
            except Exception as e:
                error_msg = f"Unexpected error with {source.name}: {str(e)}"
                logger.error(error_msg)
                source.last_error = str(e)
                continue

        # All sources failed
        self.save_sources()
        return False, None, "All TitleDB sources failed"

    def add_source(
        self, name: str, base_url: str, priority: int = 50, enabled: bool = True, source_type: str = "json"
    ) -> bool:
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
                if "base_url" in kwargs:
                    source.base_url = kwargs["base_url"].rstrip("/")
                if "enabled" in kwargs:
                    source.enabled = kwargs["enabled"]
                if "priority" in kwargs:
                    source.priority = kwargs["priority"]
                if "source_type" in kwargs:
                    source.source_type = kwargs["source_type"]

                self.save_sources()
                logger.info(f"Updated TitleDB source: {name}")
                return True

        logger.warning(f"Source {name} not found")
        return False

    def get_sources_status(self) -> List[Dict]:
        """Get status of all sources using cached dates"""
        # Load settings to check auto_use_latest
        try:
            from settings import load_settings
            app_settings = load_settings()
            auto_use_latest = app_settings.get("titles", {}).get("auto_use_latest", False)
        except:
            auto_use_latest = False

        def sort_key(s):
            if s.remote_date:
                try:
                    remote_ts = ensure_utc(s.remote_date).timestamp()
                except:
                    remote_ts = 0
            else:
                remote_ts = 0
                
            prio = s.priority
            
            if auto_use_latest and remote_ts > 0:
                return (-remote_ts, prio, s.name)
            else:
                return (prio, -remote_ts, s.name)

        sorted_sources = sorted(self.sources, key=sort_key)
        return [s.to_dict() for s in sorted_sources]

    def refresh_remote_dates(self, force=False):
        """Asynchronously refresh remote dates for all enabled sources"""
        import threading
        import time

        now = time.time()
        # Cooldown: 12 hours (43200 seconds)
        if not force and (now - self.last_refresh_time) < 43200:
            return

        self.last_refresh_time = now
        thread = threading.Thread(target=self._refresh_remote_dates_worker)
        thread.daemon = True
        thread.start()

    def _refresh_remote_dates_worker(self):
        """Worker thread for remote date refreshing"""
        from settings import load_settings
        import titledb

        logger.info("Starting background TitleDB remote date refresh...")
        app_settings = load_settings()
        region = app_settings["titles"].get("region", "US")
        language = app_settings["titles"].get("language", "en")
        possible_files = titledb.get_region_titles_filenames(region, language)

        logger.info(f"Targeting files: {possible_files} for region {region}/{language}")

        for source in self.sources:
            if not source.enabled:
                continue

            source.is_fetching = True
            try:
                logger.info(f"Checking remote date for source: {source.name}...")
                new_date = source.get_last_modified_date(possible_files)
                if new_date:
                    source.remote_date = new_date
                    logger.info(f"Source {source.name} remote date updated to {new_date}")
                else:
                    logger.info(
                        f"Could not find remote date for source: {source.name} (This is normal for some sources)"
                    )
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
