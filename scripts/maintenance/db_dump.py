import os
import sys

# Add the 'app' directory to the path 
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import create_app
from db import db, Files, Apps, Titles, Wishlist

app = create_app()
with app.app_context():
    print(f"Checking database: {db.engine.url}")
    
    # List ALL Wishlist items
    items = Wishlist.query.all()
    print(f"Total Wishlist items: {len(items)}")
    for item in items:
        print(f" - {item.name} | ID: {item.title_id} | Added: {item.added_date}")

    # List some Files
    files_count = Files.query.count()
    print(f"\nTotal Files in DB: {files_count}")
    if files_count > 0:
        latest_files = Files.query.order_by(Files.id.desc()).limit(10).all()
        for f in latest_files:
            print(f" - ID: {f.id} | Filename: {f.filename} | Identified: {f.identified}")
