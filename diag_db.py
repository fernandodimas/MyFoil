
import os
import sys
import logging

# Setup basic logging to stdout
logging.basicConfig(level=logging.INFO)

# Add 'app' to sys.path
sys.path.append(os.path.abspath('app'))

try:
    from app import app, CELERY_ENABLED
    from db import db, Files, Libraries
    import state

    with app.app_context():
        print(f"CELERY_ENABLED: {CELERY_ENABLED}")
        print(f"DATABASE_URL: {os.environ.get('DATABASE_URL', 'NOT SET')}")
        
        # Check active scans
        from job_tracker import job_tracker
        active_jobs = job_tracker.get_active_jobs()
        print(f"ACTIVE JOBS: {active_jobs}")
        
        # Check TitleDB lock
        print(f"TITLED B UPDATE RUNNING: {state.is_titledb_update_running}")
        
        # Check Libraries
        libs = Libraries.query.all()
        print(f"LIBRARIES IN DB: {[(l.id, l.path) for l in libs]}")
        
        # Check Files
        files_count = Files.query.count()
        print(f"TOTAL FILES IN DB: {files_count}")
        
        skyrim_files = Files.query.filter(Files.filename.contains('Skyrim')).all()
        print(f"SKYRIM FILES IN DB: {len(skyrim_files)}")
        for f in skyrim_files:
            print(f"  ID: {f.id}, Filename: {f.filename}, Folder: {f.folder}, Identified: {f.identified}, Path: {f.filepath}")

except Exception as e:
    print(f"DIAGNOSTIC FAILED: {e}")
    import traceback
    traceback.print_exc()
