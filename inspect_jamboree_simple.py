import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import app, db
from db import Titles, Apps, Files

with app.app_context():
    base_id = "0100965017338000"
    print(f"--- Inspecting Title: {base_id} ---")
    title = Titles.query.filter_by(title_id=base_id).first()
    if title:
        print(f"ID: {title.id}, UpdateStatus: {title.up_to_date}")
        apps = Apps.query.filter_by(title_id=title.id).all()
        for a in apps:
            print(f"App: {a.app_id} (v{a.app_version}) Type={a.app_type} Owned={a.owned}")
            for f in a.files:
                print(f"  File: {f.filename}")
    else:
        print("Base Title NOT found.")

    upd_id = "0100965017338800"
    print(f"\n--- Checking Update Title: {upd_id} ---")
    title2 = Titles.query.filter_by(title_id=upd_id).first()
    if title2:
        print(f"FOUND SEPARATE TITLE: {title2.name}")
        apps = Apps.query.filter_by(title_id=title2.id).all()
        for a in apps:
             print(f"App: {a.app_id} (v{a.app_version})")
             for f in a.files:
                 print(f"  File: {f.filename}")
    else:
         print("Update Title NOT found.")
