"""
TitleDB Update Module for Myfoil
Enhanced with multiple source support and direct JSON downloads
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

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


def download_titledb_file(filename: str, force: bool = False, silent_404: bool = False) -> bool:
    """
    Download a single TitleDB file using the source manager
    
    Args:
        filename: Name of the file to download
        force: Force download even if file exists and is recent
        silent_404: If True, do not log an error for 404 Not Found
        
    Returns:
        True if successful, False otherwise
    """
    dest_path = os.path.join(TITLEDB_DIR, filename)
    
    # Check if update is needed
    if not force and not is_file_outdated(dest_path, max_age_hours=24):
        logger.info(f"{filename} is up to date, skipping download")
        return True
    
    # Download using source manager
    source_manager = get_source_manager()
    success, source_name, error = source_manager.download_file(filename, dest_path)
    
    if success:
        logger.info(f"Successfully downloaded {filename} from {source_name}")
        return True
    else:
        if silent_404 and "404" in str(error):
            logger.debug(f"{filename} not found on sources (404), skipping silently")
        else:
            logger.error(f"Failed to download {filename}: {error}")
        return False


def update_titledb_files(app_settings: Dict, force: bool = False) -> Dict[str, bool]:
    """
    Update all required TitleDB files
    
    Args:
        app_settings: Application settings dictionary
        force: Force update even if files are recent
        
    Returns:
        Dictionary mapping filename to success status
    """
    results = {}
    
    # Core files that are always needed
    core_files = [
        'cnmts.json',
        'versions.json',
        'versions.txt',
        'languages.json',
    ]
    
    # Download core files
    for filename in core_files:
        logger.info(f"Updating {filename}...")
        results[filename] = download_titledb_file(filename, force=force)
    
    # Download region-specific titles file
    region_titles_file = get_region_titles_file(app_settings)
    logger.info(f"Updating {region_titles_file}...")
    
    # Try region-specific file first
    if download_titledb_file(region_titles_file, force=force, silent_404=True):
        results[region_titles_file] = True
    else:
        # Fallback 1: Try US/en which is almost always available and complete
        fallback_file = "titles.US.en.json"
        logger.info(f"{region_titles_file} not available, trying fallback to {fallback_file}...")
        
        if download_titledb_file(fallback_file, force=force, silent_404=True):
            # Copy to region-specific path so app can find it
            try:
                import shutil
                shutil.copy2(os.path.join(TITLEDB_DIR, fallback_file), os.path.join(TITLEDB_DIR, region_titles_file))
                results[region_titles_file] = True
                logger.info(f"Using {fallback_file} as {region_titles_file}")
            except Exception as e:
                logger.error(f"Failed to copy {fallback_file}: {e}")
                results[region_titles_file] = False
        else:
            # Fallback 2: Try generic titles.json
            logger.warning(f"Failed to download {fallback_file}, trying generic titles.json")
            if download_titledb_file('titles.json', force=force):
                # Copy generic to region-specific
                generic_path = os.path.join(TITLEDB_DIR, 'titles.json')
                region_path = os.path.join(TITLEDB_DIR, region_titles_file)
                try:
                    import shutil
                    shutil.copy2(generic_path, region_path)
                    results[region_titles_file] = True
                    logger.info(f"Using generic titles.json as {region_titles_file}")
                except Exception as e:
                    logger.error(f"Failed to copy titles.json: {e}")
                    results[region_titles_file] = False
            else:
                results[region_titles_file] = False
    
    # Update version tracking
    version_file = os.path.join(TITLEDB_DIR, '.latest')
    try:
        with open(version_file, 'w') as f:
            f.write(get_version_hash())
    except Exception as e:
        logger.warning(f"Failed to update version file: {e}")
    
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
