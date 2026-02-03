import sys
import os

# Add app to sys.path
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import app
from db import db, Titles, Apps, Files
import titles

def debug_octopath():
    with app.app_context():
        # Search by specific ID
        tid_base = "01005270232F2000"
        t = Titles.query.filter_by(title_id=tid_base).first()
        
        if not t:
            print(f"Title {tid_base} not found in DB.")
            return

        print(f"Title: {t.name}")
        print(f"  TitleID: {t.title_id}")
        
        # Get Apps
        apps = Apps.query.filter_by(title_id=t.id).all()
        owned_versions = []
        for a in apps:
            files_count = len(a.files)
            print(f"  App: {a.app_id} (Type: {a.app_type}, Ver: {a.app_version}) - Files: {files_count}")
            if files_count > 0:
                print(f"    -> Link detected. Version {a.app_version}")
                owned_versions.append(int(a.app_version) if a.app_version else 0)
                for f in a.files:
                    print(f"       File: {f.filename}")
        
        max_owned = max(owned_versions) if owned_versions else 0
        print(f"  Calculated Owned Version: {max_owned}")
        
        # Check Latest Version from TitleDB
        # Using titles.get_all_existing_versions instead, as expected by logic
        try:
             versions = titles.get_all_existing_versions(t.title_id)
             if versions:
                 latest_v = max(versions, key=lambda x: x["version"])
                 print(f"  Latest Version Available (TitleDB): {latest_v['version']} (Date: {latest_v['release_date']})")
                 
                 if max_owned >= latest_v['version']:
                    print("  Status: UP TO DATE")
                 else:
                    print("  Status: UPDATE AVAILABLE")
             else:
                 print("  No versions found in TitleDB.")
        except Exception as e:
            print(f"  Error getting versions: {e}")
            
        print("-" * 30)

if __name__ == "__main__":
    debug_octopath()
