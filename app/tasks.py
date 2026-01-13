from celery_app import celery
from flask import Flask
from db import db
from library import scan_library_path, identify_library_files, update_titles, generate_library
import titles as titles_lib
import os
import logging

logger = logging.getLogger('main')

def create_app_context():
    """Create a minimal app context for celery tasks"""
    app = Flask(__name__)
    # We need to reach constants for DB path
    from constants import DB_FILE, SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

flask_app = create_app_context()

@celery.task(name='tasks.scan_library_async')
def scan_library_async(library_path):
    """Full library scan in background"""
    with flask_app.app_context():
        from db import remove_missing_files_from_db
        logger.info(f"Background task: Starting scan for {library_path}")
        
        # 1. Cleanup missing files first
        remove_missing_files_from_db()
        
        # 2. Scan for new files
        scan_library_path(library_path)
        
        # 3. Identify new/unidentified files
        identify_library_files(library_path)
        
        # 4. Update title statuses and regenerate cache
        update_titles()
        generate_library(force=True)
        
        logger.info(f"Background task: Scan and cleanup completed for {library_path}")
        return True

@celery.task(name='tasks.identify_file_async')
def identify_file_async(filepath):
    """Identify a single file in background (e.g. from watchdog)"""
    with flask_app.app_context():
        from db import remove_missing_files_from_db
        logger.info(f"Background task: Processing library update after change in {filepath}")
        
        # For simple file changes, we can just run the global cleanup and identification
        remove_missing_files_from_db()
        
        from library import Libraries
        libraries = Libraries.query.all()
        for lib in libraries:
            identify_library_files(lib.path)
            
        update_titles()
        generate_library(force=True)
        return True
@celery.task(name='tasks.scan_all_libraries_async')
def scan_all_libraries_async():
    """Full library scan for all configured paths in background"""
    with flask_app.app_context():
        from db import remove_missing_files_from_db, get_libraries
        logger.info("Background task: Starting full library scan for all paths")
        
        remove_missing_files_from_db()
        
        libraries = get_libraries()
        for lib in libraries:
            logger.info(f"Scanning {lib.path}...")
            scan_library_path(lib.path)
            identify_library_files(lib.path)
            
        update_titles()
        generate_library(force=True)
        
        logger.info("Background task: Full scan completed.")
        return True
