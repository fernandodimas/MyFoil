from app import app, db
from app.db import Titles, Apps, Files
from sqlalchemy.orm import joinedload

with app.app_context():
    base_id = "0100965017338000"
    print(f"--- Inspecting Title: {base_id} ---")
    title = Titles.query.filter_by(title_id=base_id).first()
    if not title:
        print("Title not found!")
    else:
        print(f"Title: {title.name} (ID: {title.id})")
        print(f"Up to Date: {title.up_to_date}")
        print("Linked Apps:")
        apps = Apps.query.filter_by(title_id=title.id).all()
        for a in apps:
            print(f"  - App ID: {a.app_id}, Version: {a.app_version}, Type: {a.app_type}, Owned: {a.owned}")
            for f in a.files:
                print(f"    - File: {f.filename} (Size: {f.size})")

    print("\n--- Searching for potential Update Title IDs ---")
    # Search for titles that look like the update ID (suffix 800)
    update_id_guess = "0100965017338800"
    upd_title = Titles.query.filter_by(title_id=update_id_guess).first()
    if upd_title:
        print(f"FOUND SEPARATE TITLE RECORD for {update_id_guess}!")
        print(f"Name: {upd_title.name}")
        print("Linked Apps:")
        apps = Apps.query.filter_by(title_id=upd_title.id).all()
        for a in apps:
             print(f"  - App ID: {a.app_id}, Version: {a.app_version}, Type: {a.app_type}")
             for f in a.files:
                print(f"    - File: {f.filename}")
    else:
        print(f"No separate title record found for {update_id_guess}")

