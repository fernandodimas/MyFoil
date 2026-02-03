import sys
import os

# Add app to sys.path
sys.path.append(os.path.join(os.getcwd(), 'app'))

import app
from db import db, Titles, Apps, Files
import titles

def debug_octopath():
    with app.app_context():
        # Find Octopath Traveler
        # Note: The user called it "OCTOPATH TRAVELER 0" in previous logs, possibly filename based?
        # Let's search loosely.
        t_list = Titles.query.filter(Titles.name.ilike('%OCTOPATH%')).all()
        
        for t in t_list:
            print(f"Title: {t.name}")
            print(f"  TitleID: {t.title_id}")
            
            # Get Apps
            apps = Apps.query.filter_by(title_id=t.id).all()
            owned_versions = []
            for a in apps:
                files_count = len(a.files)
                print(f"  App: {a.app_id} (Type: {a.app_type}, Ver: {a.app_version}) - Files: {files_count}")
                if files_count > 0:
                    owned_versions.append(int(a.app_version))
                    for f in a.files:
                        print(f"    File: {f.filename} (Identified: {f.identified})")
            
            max_owned = max(owned_versions) if owned_versions else 0
            print(f"  Calculated Owned Version: {max_owned}")
            
            # Check Latest Version from TitleDB
            latest_v_info = titles.get_latest_version(t.title_id)
            latest_v = latest_v_info.get('version', 0) if latest_v_info else 0
            latest_date = latest_v_info.get('release_date', 'Unknown') if latest_v_info else 'Unknown'
            
            print(f"  Latest Version Available (TitleDB): {latest_v} (Date: {latest_date})")
            
            if max_owned >= latest_v:
                print("  Status: UP TO DATE")
            else:
                print("  Status: UPDATE AVAILABLE")
            print("-" * 30)

if __name__ == "__main__":
    debug_octopath()
