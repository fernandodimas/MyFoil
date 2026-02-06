import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import app, db
from db import Files

with app.app_context():
    file_id = 1305 
    print(f"Checking file {file_id}...")
    try:
        file = db.session.get(Files, file_id)
        if file:
            print(f"File found: {file}")
        else:
             print("File NOT found")
    except Exception as e:
        print(f"Error: {e}")
