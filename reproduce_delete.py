import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import app, db
from db import Files, Apps

with app.app_context():
    # Find any existing file
    file = Files.query.first()
    if file:
        print(f"Testing with file id: {file.id}, Path: {file.filepath}")
        
        # Simulate check in route
        file_obj = db.session.get(Files, file.id)
        if not file_obj:
            print("Route check: File not found")
        else:
             print("Route check: File FOUND")
    else:
        print("No files in DB to test with")
