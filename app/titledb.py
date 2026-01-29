"""
TitleDB Update Module for MyFoil
Enhanced with multiple source support and direct JSON downloads
"""

import os
import logging
import requests

# Retrieve main logger
logger = logging.getLogger("main")

try:
    import unzip_http

    HAS_UNZIP_HTTP = True
except ImportError:
    logger.warning("unzip-http module not found. Legacy ZIP TitleDB source will not be available.")
    HAS_UNZIP_HTTP = False
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from constants import *
from settings import load_settings
from titledb_sources import TitleDBSourceManager
from utils import format_datetime, now_utc, ensure_utc

# Retrieve main logger
logger = logging.getLogger("main")

# Global source manager instance
_source_manager: Optional[TitleDBSourceManager] = None


def get_source_manager() -> TitleDBSourceManager:
    """Get or create the global source manager instance"""
    global _source_manager
    if _source_manager is None:
        _source_manager = TitleDBSourceManager(CONFIG_DIR)
    return _source_manager


def get_region_titles_file(app_settings: Dict) -> str:
    """Get the preferred region-specific titles filename"""
    region = app_settings.get("titles", {}).get("region", "US")
    language = app_settings.get("titles", {}).get("language", "en")
    return f"titles.{region}.{language}.json"


def get_region_titles_filenames(region: str, language: str) -> List[str]:
    """Get possible filenames for regional titles"""
    return [f"titles.{region}.{language}.json", f"{region}.{language}.json"]


def get_version_hash() -> str:
    """Get a simple version hash based on current timestamp"""
    return now_utc().strftime("%Y%m%d%H%M%S")


def is_file_outdated(filepath: str, max_age_hours: int = 24) -> bool:
    """Check if a file is older than max_age_hours or is empty"""
    if not os.path.exists(filepath):
        return True

    # Check if file is empty
    if os.path.getsize(filepath) == 0:
        return True

    file_time = datetime.fromtimestamp(os.path.getmtime(filepath), tz=timezone.utc)
    age = now_utc() - file_time
    return age.total_seconds() > (max_age_hours * 3600)


def download_titledb_legacy(
    source_name: str, base_url: str, filename: str, dest_path: str
) -> Tuple[bool, Optional[str]]:
    """Helper to download a file from the legacy TitleDB ZIP source"""
    try:
        # Get the direct URL from the artifact redirector
        r = requests.get(base_url, allow_redirects=False, timeout=10)
        direct_url = r.next.url if hasattr(r, "next") else base_url

        rzf = unzip_http.RemoteZipFile(direct_url)

        # Check if file exists in zip
        zip_filenames = [f.filename for f in rzf.infolist()]
        if filename not in zip_filenames:
            return False, f"File {filename} not found in remote ZIP"

        with rzf.open(filename) as fpin:
            with open(dest_path, mode="wb") as fpout:
                while True:
                    chunk = fpin.read(65536)
                    if not chunk:
                        break
                    fpout.write(chunk)

        return True, None
    except Exception as e:
        return False, str(e)


def download_titledb_file(filename: str, force: bool = False, silent_404: bool = False) -> bool:
    """
    Download a single TitleDB file using the source manager.
    The source_manager handles fallback and error handling automatically.
    """
    dest_path = os.path.join(TITLEDB_DIR, filename)

    # Check if update is needed
    if not force and not is_file_outdated(dest_path, max_age_hours=24):
        logger.info(f"{filename} is up to date, skipping download")
        return True

    # Use source_manager which has proper fallback logic
    source_manager = get_source_manager()
    
    # Increase timeout to 120 seconds for large files (e.g., 76MB US.en.json)
    success, source_name, error = source_manager.download_file(filename, dest_path, timeout=120, silent_404=silent_404)
    
    if success:
        logger.info(f"Successfully downloaded {filename} from {source_name}")
        return True
    else:
        error_str = str(error) if error else ""
        if silent_404 and ("404" in error_str or "not found" in error_str.lower()):
            logger.debug(f"{filename} not found (404), skipping silently")
        else:
            logger.warning(f"Failed to download {filename}: {error}")
        return False


def update_titledb_files(app_settings: Dict, force: bool = False, job_id: str = None) -> Dict[str, bool]:
    """
    Update all required TitleDB files using either Legacy ZIP or JSON sources
    """
    from job_tracker import job_tracker
    def log_tdb(msg, p=None):
        logger.info(msg)
        if job_id:
            job_tracker.update_progress(job_id, p, 10, msg)

    results = {}
    source_manager = get_source_manager()
    active_sources = source_manager.get_active_sources()

    if not active_sources:
        logger.error("No active TitleDB sources configured")
        return {}

    for source in active_sources:
        log_tdb(f"Source: {source.name}", 2)
        results = {}

        if source.source_type == "zip_legacy":
            # --- ORIGINAL PROJECT LOGIC FOR LEGACY ZIP ---
            try:
                if not HAS_UNZIP_HTTP:
                    logger.error("Cannot update from legacy ZIP: unzip-http module is missing.")
                    continue

                r = requests.get(source.base_url, allow_redirects=False, timeout=10)
                direct_url = r.next.url if hasattr(r, "next") else source.base_url
                rzf = unzip_http.RemoteZipFile(direct_url)

                # Check for update available (Legacy style)
                update_available = force
                local_commit_file = os.path.join(TITLEDB_DIR, ".latest")
                remote_latest_commit_file = [f.filename for f in rzf.infolist() if "latest_" in f.filename][0]
                latest_remote_commit = remote_latest_commit_file.split("_")[-1]

                if not os.path.isfile(local_commit_file):
                    update_available = True
                else:
                    with open(local_commit_file, "r") as f:
                        current_commit = f.read()
                    if current_commit != latest_remote_commit:
                        update_available = True

                # FORCE update if critical files are missing from disk
                region_titles_file = get_region_titles_file(app_settings)
                fallback_titles_file = "titles.US.en.json"
                ultimate_fallback = "titles.json"
                critical_files = [
                    "cnmts.json",
                    "versions.json",
                    region_titles_file,
                    fallback_titles_file,
                    ultimate_fallback,
                ]
                missing_critical = any(not os.path.exists(os.path.join(TITLEDB_DIR, f)) for f in critical_files)


                if missing_critical:
                    logger.info("Critical TitleDB files missing from disk, forcing extraction...")
                    update_available = True

                if update_available:
                    zip_files = [f.filename for f in rzf.infolist()]

                    # Always ensure we try to get core files + region + fallback safety net
                    files_to_update = [
                        "cnmts.json",
                        "versions.json",
                        "languages.json",
                        region_titles_file,
                        fallback_titles_file,
                        ultimate_fallback,
                    ]

                    # Update all files from ZIP - handles potential paths in ZIP
                    for filename in files_to_update:
                        # Try exact match or match with path
                        target_zip_path = None
                        if filename in zip_files:
                            target_zip_path = filename
                        else:
                            # Try to find file if it's inside a folder in the zip
                            for zf in zip_files:
                                if zf.endswith("/" + filename) or zf.endswith("\\" + filename):
                                    target_zip_path = zf
                                    break

                        if target_zip_path:
                            log_tdb(f"Extracting {filename}...", 4)
                            try:
                                with rzf.open(target_zip_path) as fpin:
                                    with open(os.path.join(TITLEDB_DIR, filename), "wb") as fpout:
                                        while True:
                                            chunk = fpin.read(65536)
                                            if not chunk:
                                                break
                                            fpout.write(chunk)
                                results[filename] = True
                            except Exception as ex:
                                logger.error(f"Failed to extract {filename}: {ex}")
                                results[filename] = False

                    # Save new commit hash
                    with open(local_commit_file, "w") as f:
                        f.write(latest_remote_commit)

                    source.last_success = now_utc()
                    source.last_error = None
                else:
                    logger.info("TitleDB already up to date (Legacy)")
                    for f in ["cnmts.json", "versions.json", "languages.json", get_region_titles_file(app_settings)]:
                        results[f] = True

                source_manager.save_sources()
                return results  # Success!
            except Exception as e:
                logger.error(f"Legacy update from {source.name} failed: {e}")
                source.last_error = str(e)
                source_manager.save_sources()
                continue  # Try next source

        else:
            # --- NEW JSON MULTI-SOURCE LOGIC ---
            try:
                log_tdb(f"Downloading core files from {source.name}...", 3)
                core_files = ["cnmts.json", "versions.json", "languages.json"]
                for filename in core_files:
                    results[filename] = download_titledb_file(filename, force=force)

                # PRIORITY: Try to download the region-specific file based on settings FIRST
                region = app_settings["titles"].get("region", "US")
                language = app_settings["titles"].get("language", "en")
                region_filenames = get_region_titles_filenames(region, language)

                log_tdb(f"Downloading regional titles ({region}.{language})...", 5)
                region_success = False
                for region_filename in region_filenames:
                    logger.info(f"Attempting to download region-specific file: {region_filename}")
                    if download_titledb_file(region_filename, force=force, silent_404=True):
                        region_success = True
                        results[region_filename] = True
                        break

                results["region_titles"] = region_success

                # Only try titles.json if region failed, as a last resort
                if not region_success:
                    logger.warning(f"Region-specific files {region_filenames} not available, trying titles.json as fallback...")
                    download_titledb_file("titles.json", force=force, silent_404=True)

                if all(results.get(f) for f in core_files):
                    source.last_success = now_utc()
                    source.last_error = None
                    source_manager.save_sources()
                    
                    # Log which regional results we got
                    if region_success:
                         log_tdb(f"✓ Downloaded TitleDB from {source.name}", 8)
                    else:
                         logger.warning(f"Source {source.name} NO region-specific titles.")
                    
                    return results
                else:
                    logger.warning(f"JSON source {source.name} failed to provide core files.")
                    continue
            except Exception as e:
                logger.error(f"JSON update from {source.name} failed: {e}")
                source.last_error = str(e)
                source_manager.save_sources()
                continue  # Try next source

    return {}


def update_titledb(app_settings: Dict, force: bool = False) -> bool:
    """
    Main entry point for updating TitleDB

    Args:
        app_settings: Application settings dictionary
        force: Force update even if files are recent

    Returns:
        True if all files updated successfully, False otherwise
    """
    from job_tracker import job_tracker, JobType
    from socket_helper import get_socketio_emitter
    import time

    job_tracker.set_emitter(get_socketio_emitter())

    job_id = f"titledb_{int(time.time())}"
    job_tracker.start_job(job_id, JobType.TITLEDB_UPDATE, "Updating TitleDB")

    try:
        logger.info("Updating TitleDB...")

        # Ensure TitleDB directory exists
        os.makedirs(TITLEDB_DIR, exist_ok=True)

        # Update all files
        job_tracker.update_progress(job_id, 10, message="Downloading files...")
        results = update_titledb_files(app_settings, force=force, job_id=job_id)

        # Check results
        success_count = sum(1 for v in results.values() if v)
        total_count = len(results)

        if success_count > 0:
            job_tracker.update_progress(job_id, 90, message="Reloading database...")
            import titles

            titles.load_titledb(force=True)

        if success_count == total_count:
            job_tracker.complete_job(job_id, f"Updated {success_count}/{total_count} files")
            # complete_job already emits via configured emitter
            logger.info(f"TitleDB update completed successfully ({success_count}/{total_count} files)")
            return True
        else:
            msg = f"Partial update: {success_count}/{total_count}"
            job_tracker.complete_job(job_id, msg)
            # complete_job already emits via configured emitter
            logger.warning(f"TitleDB update completed with errors ({success_count}/{total_count} files succeeded)")
            return False

    except Exception as e:
        job_tracker.fail_job(job_id, str(e))
        # fail_job already emits via configured emitter
        return False


def get_titledb_sources_status() -> List[Dict]:
    """Get status of all configured TitleDB sources"""
    source_manager = get_source_manager()
    return source_manager.get_sources_status()


def get_active_source_info() -> Dict:
    """Get information about the currently active/latest successful source"""
    source_manager = get_source_manager()
    sources = source_manager.get_active_sources()

    # Sort by last success time (descending) to find the most recently used
    successful_sources = [s for s in sources if s.last_success]
    successful_sources.sort(key=lambda s: ensure_utc(s.last_success), reverse=True)

    if successful_sources:
        active = successful_sources[0]
        # Calculate time since update using UTC to match last_success
        # Ensure aware datetime for comparison to avoid offset-naive vs offset-aware error
        last_success = ensure_utc(active.last_success)
        time_since = now_utc() - last_success
        is_updated = time_since.total_seconds() < (24 * 3600)  # Considered updated if < 24h

        # Use cached remote_date if available, otherwise fetch it
        remote_date = active.remote_date
        if not remote_date:
            # Fetch remote date using versions files as the main indicator
            remote_date = active.get_last_modified_date(["versions.json", "versions.txt"])
            # Cache it in the object for this session
            active.remote_date = remote_date

        remote_date_str = "Unknown"
        if remote_date:
            remote_date_str = format_datetime(remote_date)

        # Get which titles file is actually loaded
        import titles

        loaded_file = titles.get_loaded_titles_file() or "Not loaded yet"

        # Check if update is available
        update_available = False
        if remote_date and active.last_success:
            comp_remote = ensure_utc(remote_date)
            comp_success = ensure_utc(active.last_success)
            
            # If remote date is newer than last download (with 1min margin)
            if comp_remote > (comp_success + timedelta(minutes=1)):
                update_available = True
        
        # Format dates for UI
        last_download_date = format_datetime(active.last_success)
        
        # Get cache timestamp from titles module (real reading/sanitization)
        cache_ts = titles.get_titledb_cache_timestamp()
        last_process_date = "Never"
        if cache_ts:
            from datetime import datetime
            dt_processed = datetime.fromtimestamp(cache_ts, tz=timezone.utc)
            last_process_date = format_datetime(dt_processed)
        
        return {
            "name": active.name,
            "last_success": active.last_success,
            "is_updated": is_updated,
            "update_available": update_available,
            "time_since": str(time_since).split(".")[0],
            "last_download_date": last_download_date,
            "last_process_date": last_process_date,
            "titles_count": titles.get_titles_count(),
            "remote_date": remote_date_str,
            "loaded_titles_file": loaded_file,
            "is_fetching": getattr(active, "is_fetching", False),
            "last_error": getattr(active, "last_error", None),
        }

    return None


def add_titledb_source(name: str, base_url: str, priority: int = 50, enabled: bool = True) -> bool:
    """Add a new TitleDB source"""
    source_manager = get_source_manager()
    return source_manager.add_source(name, base_url, priority, enabled)


def remove_titledb_source(name: str) -> bool:
    """Remove a TitleDB source"""
    source_manager = get_source_manager()
    return source_manager.remove_source(name)


def update_titledb_source(name: str, **kwargs) -> bool:
    """Update a TitleDB source"""
    source_manager = get_source_manager()
    return source_manager.update_source(name, **kwargs)


def update_titledb_priorities(priority_map: Dict[str, int]) -> bool:
    """Batch update priorities"""
    source_manager = get_source_manager()
    return source_manager.update_priorities(priority_map)


def refresh_titledb_remote_dates():
    """Trigger background refresh of remote dates for all sources"""
    source_manager = get_source_manager()
    source_manager.refresh_remote_dates()
