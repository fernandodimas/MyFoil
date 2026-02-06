from app import app, db
from app.db import Files, Apps

with app.app_context():
    file_id = 1305 # From USER error Report
    file = db.session.get(Files, file_id)
    if file:
        print(f"File found: {file.filename} (ID: {file.id})")
        print(f"Linked to {len(file.apps)} apps")
        for app in file.apps:
             print(f" - App: {app.app_id}")
    else:
        print("File not found in DB")
