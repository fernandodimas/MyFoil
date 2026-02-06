import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import app, db
from db import Titles, Apps, Files
from sqlalchemy.orm import joinedload

with app.app_context():
    tid = "0100C62011050000"
    print(f"--- Inspecting Game Boy: {tid} ---")
    title = Titles.query.filter_by(title_id=tid).first()
    if title:
        print(f"Title: {title.name}")
        print(f"Up to Date (DB flag): {title.up_to_date}")
        owned_apps = Apps.query.filter_by(title_id=title.id, owned=True).all()
        print(f"Owned Apps count: {len(owned_apps)}")
        for a in owned_apps:
            print(f"  App: {a.app_id}, Version: {a.app_version}, Files count: {len(a.files)}")
            for f in a.files:
                print(f"    - File: {f.filename}")
    else:
        print("Game Boy Title record NOT found.")

