
import os
import sys

# Add 'app' directory to sys.path
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import create_app
from db import db, Titles, Apps, Files, TitleMetadata

app = create_app()

def diagnostic():
    with app.app_context():
        print(f"Database URL: {app.config['SQLALCHEMY_DATABASE_URI']}")
        
        # 1. List sample titles to verify DB content
        print("\n--- Listing first 10 Titles in DB ---")
        all_titles = Titles.query.limit(10).all()
        for t in all_titles:
            print(f"[{t.title_id}] {t.name}")

        # 2. Check for specific TitleID from screenshot
        target_ids = ["0100453019AA8000", "0100965017338000"]
        for tid in target_ids:
            print(f"\n--- Searching for ID '{tid}' ---")
            # Try case-insensitive search just in case
            title = Titles.query.filter(Titles.title_id.ilike(f"%{tid}%")).first()
            
            if not title:
                print("Title NOT found.")
                continue
            
            print(f"TITLE FOUND: {title.name} (ID: {title.title_id})")
            
            # Check apps
            apps = Apps.query.filter_by(title_id=title.id).all()
            owned_updates = 0
            valid_update_files = 0
            
            for a in apps:
                if a.app_type == "UPDATE":
                    print(f"  APP: {a.app_id} (Type: {a.app_type}, Version: {a.app_version}, Owned: {a.owned})")
                    
                    # Check direct file relationship
                    for f in a.files:
                        print(f"    FILE (DB): {f.filename}")
                        print(f"      Identified: {f.identified}")
                        print(f"      Error: {f.identification_error}")
                        print(f"      Path: {f.filepath}")
                        
                        if a.owned and not f.identification_error and f.identified and f.filepath:
                            valid_update_files += 1
                            
                    # Check files_info structure if we were simulate the API logic
                    # (Not possible directly on DB object without helper, but good enough)
            
            print(f"  -> Valid update files found: {valid_update_files}")
            
            # This block should be outside the 'for a in apps' loop, but inside the 'for tid in target_ids' loop
            print(f"  -> Valid update files for redundant check: {valid_update_files}")
            if valid_update_files > 1:
                print("  -> SHOULD BE MARKED AS REDUNDANT")
            else:
                print("  -> SHOULD NOT BE MARKED AS REDUNDANT")

        # 2. Check worker status if possible
        print("\n--- Recent worker activity ---")
        try:
            from db import ActivityLog
            logs = ActivityLog.query.filter(ActivityLog.activity_type.ilike("%worker%")).order_by(ActivityLog.timestamp.desc()).limit(10).all()
            for log in logs:
                print(f"{log.timestamp}: {log.activity_type} - {log.details}")
        except Exception as e:
            print(f"Could not read ActivityLog: {e}")

if __name__ == "__main__":
    diagnostic()
