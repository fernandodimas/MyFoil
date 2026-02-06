import sys
import os
sys.path.append('app')
from app import create_app
from db import db, Files, Apps, Titles, TitleDBCache, TitleDBVersions, TitleDBDLCs

app = create_app()
with app.app_context():
    try:
        print("Cleaning game database...")
        
        # Order matters for foreign keys if not using CASCADE in SQL directly
        print("Truncating files, apps and titles...")
        
        # Direct SQL to handle association tables and constraints easily
        db.session.execute(db.text("TRUNCATE TABLE app_files CASCADE;"))
        db.session.execute(db.text("TRUNCATE TABLE files CASCADE;"))
        db.session.execute(db.text("TRUNCATE TABLE apps CASCADE;"))
        db.session.execute(db.text("TRUNCATE TABLE titles CASCADE;"))
        db.session.execute(db.text("TRUNCATE TABLE titledb_cache CASCADE;"))
        db.session.execute(db.text("TRUNCATE TABLE titledb_versions CASCADE;"))
        db.session.execute(db.text("TRUNCATE TABLE titledb_dlcs CASCADE;"))
        
        db.session.commit()
        print("SUCCESS: Database cleaned. Run a 'Full Scan' to re-index your games.")
    except Exception as e:
        db.session.rollback()
        print(f"FAILED: {e}")
