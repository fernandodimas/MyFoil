import os
import sys

# Add the 'app' directory to the path 
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import create_app
from db import db, Files, Apps, Titles

app = create_app()
with app.app_context():
    # Search for files with the ID in filename
    query = Files.query.filter(Files.filename.ilike('%01001B300B9BE800%')).all()
    print(f"Found {len(query)} files in database matching '01001B300B9BE800'")
    
    for f in query:
        print(f"\n--- File Info ---")
        print(f"ID: {f.id}")
        print(f"Filename: {f.filename}")
        print(f"Identified: {f.identified}")
        print(f"Error: {f.identification_error}")
        
        if f.apps:
            print(f"Linked Apps (IDs): {[a.app_id for a in f.apps]}")
            for a in f.apps:
                print(f"  App Type: {a.app_type}, Version: {a.app_version}")
                if a.title:
                    print(f"  Title: {a.title.name} ({a.title.title_id})")
        else:
            print("No apps linked to this file record.")

    if not query:
        # Maybe it's not in the DB yet? Scan?
        print("File not found in database. Checking disk...")
        for root, dirs, files in os.walk('/games'): # Assuming /games as per user screenshot
             for file in files:
                 if '01001B300B9BE800' in file:
                     print(f"Found on disk: {os.path.join(root, file)}")
