import os
import re
import shutil
import logging
from db import db, Files, Titles
from titles import get_game_info

logger = logging.getLogger('main')

PLACEHOLDERS = {
    '{Name}': 'Game Name',
    '{TitleID}': 'Title ID (16 chars)',
    '{Version}': 'Version Number (e.g. 65536)',
    '{DisplayVersion}': 'Human Readable Version (e.g. 1.0.0)',
    '{Region}': 'Region (US, EU, JP, etc)',
    '{Type}': 'Type (BASE, UPD, DLC)',
    '{Ext}': 'File Extension (nsp, xci, etc)'
}

def sanitize_filename(filename):
    """Sanitize filename to remove illegal characters for filesystems"""
    # Remove sensitive chars
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()

def get_file_metadata(file_id):
    """Gather all metadata needed for renaming a specific file"""
    file_entry = Files.query.get(file_id)
    if not file_entry:
        return None

    # Get associated App and Title
    # A file can be associated with multiple apps (multi-content), 
    # but for renaming we generally pick the primary one or the first one.
    # We prefer the one that matches the file's main purpose.
    
    # Heuristic: If it has multiple apps, pick the one that matches the file's identification if possible
    # For now, just pick the first main app
    app_entry = None
    if file_entry.apps:
        app_entry = file_entry.apps[0]
    
    if not app_entry:
        logger.warning(f"File {file_entry.filename} has no identified app, cannot rename.")
        return None

    title_entry = Titles.query.filter_by(id=app_entry.title_id).first()
    title_info = get_game_info(title_entry.title_id) if title_entry else {}
    
    # Determine Region (heuristic based on title info or filename)
    # Try to extract region from existing filename if standard pattern
    # Or just use "World" if unknown
    
    # Calculate Display Version
    version = int(app_entry.app_version)
    display_version = f"{version}"
    if version >= 65536 and version % 65536 == 0:
         # Rough estimation for update versions if we had the logic, 
         # but raw version is safer unless we implement semantic version parsing
         pass

    metadata = {
        'Name': title_info.get('name', 'Unknown Game'),
        'TitleID': app_entry.app_id, # Use App ID for the file (updates have different IDs)
        'Version': str(version),
        'DisplayVersion': display_version,
        'Region': 'World', # Placeholder for now
        'Type': app_entry.app_type,
        'Ext': file_entry.extension
    }
    
    return metadata

def start_renaming_job(patterns):
    """
    Renames files in the library based on the provided patterns.
    patterns: dict = {'BASE': 'pattern...', 'UPD': 'pattern...', 'DLC': 'pattern...'}
    """
    logger.info("Starting library renaming job...")
    
    files = Files.query.all()
    count = 0
    errors = 0
    
    for file in files:
        try:
            metadata = get_file_metadata(file.id)
            if not metadata:
                continue
                
            ptype = metadata['Type']
            pattern = patterns.get(ptype)
            
            if not pattern:
                continue
            
            # Format the new name
            new_name = pattern
            for key, value in metadata.items():
                new_name = new_name.replace(f"{{{key}}}", str(value))
            
            new_name = sanitize_filename(new_name)
            new_name = f"{new_name}.{metadata['Ext']}"
            
            # Check if rename is needed
            if new_name == file.filename:
                continue
                
            # Perform Rename
            old_path = file.filepath
            new_path = os.path.join(file.folder, new_name)
            
            if os.path.exists(new_path):
                logger.warning(f"Cannot rename {file.filename} to {new_name}: Target exists.")
                errors += 1
                continue
                
            shutil.move(old_path, new_path)
            
            # Update Database
            file.filename = new_name
            file.filepath = new_path
            db.session.commit()
            count += 1
            
        except Exception as e:
            logger.error(f"Error renaming file {file.id}: {e}")
            errors += 1
            
    logger.info(f"Renaming job finished. Renamed {count} files. Errors: {errors}")
    return count, errors
