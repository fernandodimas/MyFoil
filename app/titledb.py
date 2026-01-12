"""
TitleDB Update Module for Myfoil
Enhanced with multiple source support and direct JSON downloads
"""
import os
import json
import logging
import requests
import unzip_http
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from constants import *
from titledb_sources import TitleDBSourceManager

# Retrieve main logger
logger = logging.getLogger('main')

# Global source manager instance
_source_manager: Optional[TitleDBSourceManager] = None


def get_source_manager() -> TitleDBSourceManager:
    """Get or create the global source manager instance"""
    global _source_manager
    if _source_manager is None:
        _source_manager = TitleDBSourceManager(CONFIG_DIR)
    return _source_manager


def get_region_titles_file(app_settings: Dict) -> str:
    """Get the region-specific titles filename"""
    region = app_settings['titles']['region']
    language = app_settings['titles']['language']
    
    # Try both naming conventions
    # blawar/titledb uses: titles.US.en.json
    # Some sources use: titles.json (generic)
    return f"titles.{region}.{language}.json"


def get_version_hash() -> str:
    """Get a simple version hash based on current timestamp"""
    return datetime.now().strftime("%Y%m%d%H%M%S")


def is_file_outdated(filepath: str, max_age_hours: int = 24) -> bool:
    """Check if a file is older than max_age_hours"""
    if not os.path.exists(filepath):
        return True
    
    file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
    age = datetime.now() - file_time
    return age.total_seconds() > (max_age_hours * 3600)


def download_titledb_legacy(source_name: str, base_url: str, filename: str, dest_path: str) -> Tuple[bool, Optional[str]]:
    """Helper to download a file from the legacy TitleDB ZIP source"""
    try:
        # Get the direct URL from the artifact redirector
        r = requests.get(base_url, allow_redirects=False, timeout=10)
        direct_url = r.next.url if hasattr(r, 'next') else base_url
        
        rzf = unzip_http.RemoteZipFile(direct_url)
        
        # Check if file exists in zip
        zip_filenames = [f.filename for f in rzf.infolist()]
        if filename not in zip_filenames:
            return False, f"File {filename} not found in remote ZIP"
            
        with rzf.open(filename) as fpin:
            with open(dest_path, mode='wb') as fpout:
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
    Download a single TitleDB file using the source manager
    """
    dest_path = os.path.join(TITLEDB_DIR, filename)
    
    # Check if update is needed
    if not force and not is_file_outdated(dest_path, max_age_hours=24):
        logger.info(f"{filename} is up to date, skipping download")
        return True
    
    source_manager = get_source_manager()
    active_sources = source_manager.get_active_sources()
    
    if not active_sources:
        logger.error("No active TitleDB sources configured")
        return False
        
    for source in active_sources:
        logger.info(f"Attempting to download {filename} from {source.name} ({source.source_type})...")
        
        if source.source_type == 'zip_legacy':
            success, error = download_titledb_legacy(source.name, source.base_url, filename, dest_path)
        else:
            # Standard JSON download
            url = source.get_file_url(filename)
            try:
                response = requests.get(url, timeout=30, stream=True)
                response.raise_for_status()
                with open(dest_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                success, error = True, None
            except Exception as e:
                success, error = False, str(e)

        if success:
            source.last_success = datetime.now()
            source.last_error = None
            source_manager.save_sources()
            logger.info(f"Successfully downloaded {filename} from {source.name}")
            return True
        else:
            source.last_error = error
            if silent_404 and ("404" in str(error) or "not found" in str(error).lower()):
                logger.debug(f"{filename} not found on {source.name} (skipping silently)")
            else:
                logger.warning(f"Failed to download {filename} from {source.name}: {error}")
            continue

    source_manager.save_sources()
    return False


def update_titledb_files(app_settings: Dict, force: bool = False) -> Dict[str, bool]:
    """
    Update all required TitleDB files using either Legacy ZIP or JSON sources
    """
    results = {}
    source_manager = get_source_manager()
    active_sources = source_manager.get_active_sources()
    
    if not active_sources:
        logger.error("No active TitleDB sources configured")
        return {}

    source = active_sources[0] # Try the highest priority source
    logger.info(f"Using TitleDB source: {source.name} (Type: {source.source_type})")

    if source.source_type == 'zip_legacy':
        # --- ORIGINAL PROJECT LOGIC FOR LEGACY ZIP ---
        try:
            r = requests.get(source.base_url, allow_redirects=False, timeout=10)
            direct_url = r.next.url if hasattr(r, 'next') else source.base_url
            rzf = unzip_http.RemoteZipFile(direct_url)
            
            # Check for update available (Legacy style)
            update_available = force
            local_commit_file = os.path.join(TITLEDB_DIR, '.latest')
            remote_latest_commit_file = [f.filename for f in rzf.infolist() if 'latest_' in f.filename][0]
            latest_remote_commit = remote_latest_commit_file.split('_')[-1]

            if not os.path.isfile(local_commit_file):
                update_available = True
            else:
                with open(local_commit_file, 'r') as f:
                    current_commit = f.read()
                if current_commit != latest_remote_commit:
                    update_available = True
            
            # FORCE update if critical files are missing from disk
            region_titles_file = get_region_titles_file(app_settings)
            critical_files = ['cnmts.json', 'versions.json', region_titles_file]
            missing_critical = any(not os.path.exists(os.path.join(TITLEDB_DIR, f)) for f in critical_files)
            
            if missing_critical:
                logger.info("Critical TitleDB files missing from disk, forcing extraction...")
                update_available = True

            if update_available:
                zip_files = [f.filename for f in rzf.infolist()]
                logger.debug(f"Files found in ZIP: {', '.join(zip_files[:10])}... (Total: {len(zip_files)})")
                
                files_to_update = ['cnmts.json', 'versions.json', 'versions.txt', 'languages.json', region_titles_file]
                
                # Update all files from ZIP - handles potential paths in ZIP
                for filename in files_to_update:
                    # Try exact match or match with path
                    target_zip_path = None
                    if filename in zip_files:
                        target_zip_path = filename
                    else:
                        # Try to find file if it's inside a folder in the zip
                        for zf in zip_files:
                            if zf.endswith('/' + filename) or zf.endswith('\\' + filename):
                                target_zip_path = zf
                                break
                    
                    if target_zip_path:
                        logger.info(f'Extracting {filename} from legacy ZIP ({target_zip_path})...')
                        try:
                            with rzf.open(target_zip_path) as fpin:
                                with open(os.path.join(TITLEDB_DIR, filename), 'wb') as fpout:
                                    while True:
                                        chunk = fpin.read(65536)
                                        if not chunk: break
                                        fpout.write(chunk)
                            results[filename] = True
                        except Exception as ex:
                            logger.error(f"Failed to extract {filename}: {ex}")
                            results[filename] = False
                
                # Save new commit hash
                with open(local_commit_file, 'w') as f:
                    f.write(latest_remote_commit)
                
                source.last_success = datetime.now()
                source.last_error = None
            else:
                logger.info("TitleDB already up to date (Legacy)")
                for f in ['cnmts.json', 'versions.json', 'versions.txt', 'languages.json', get_region_titles_file(app_settings)]:
                    results[f] = True
            
            source_manager.save_sources()
        except Exception as e:
            logger.error(f"Legacy update failed: {e}")
            source.last_error = str(e)
            source_manager.save_sources()
            # If legacy fails, we don't automatedly fallback to JSON here to keep it simple and predictable
            return {}

    else:
        # --- NEW JSON MULTI-SOURCE LOGIC ---
        core_files = ['cnmts.json', 'versions.json', 'versions.txt', 'languages.json']
        for filename in core_files:
            results[filename] = download_titledb_file(filename, force=force)
        
        region_titles_file = get_region_titles_file(app_settings)
        if download_titledb_file(region_titles_file, force=force, silent_404=True):
            results[region_titles_file] = True
        else:
            # Fallback to US/en for JSON sources
            if download_titledb_file("titles.US.en.json", force=force, silent_404=True):
                shutil.copy2(os.path.join(TITLEDB_DIR, "titles.US.en.json"), os.path.join(TITLEDB_DIR, region_titles_file))
                results[region_titles_file] = True
            else:
                results[region_titles_file] = download_titledb_file('titles.json', force=force)

    return results


def update_titledb(app_settings: Dict, force: bool = False) -> bool:
    """
    Main entry point for updating TitleDB
    
    Args:
        app_settings: Application settings dictionary
        force: Force update even if files are recent
        
    Returns:
        True if all files updated successfully, False otherwise
    """
    logger.info('Updating TitleDB...')
    
    # Ensure TitleDB directory exists
    os.makedirs(TITLEDB_DIR, exist_ok=True)
    
    # Update all files
    results = update_titledb_files(app_settings, force=force)
    
    # Check results
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    if success_count == total_count:
        logger.info(f'TitleDB update completed successfully ({success_count}/{total_count} files)')
        return True
    else:
        logger.warning(f'TitleDB update completed with errors ({success_count}/{total_count} files succeeded)')
        return False


def get_titledb_sources_status() -> List[Dict]:
    """Get status of all configured TitleDB sources"""
    source_manager = get_source_manager()
    return source_manager.get_sources_status()


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
