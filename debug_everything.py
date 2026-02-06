import os
import sys

# Add the 'app' directory to the path 
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import create_app
from db import db, Files, Apps, Titles, Wishlist

app = create_app()
with app.app_context():
    print(f"Checking database: {db.engine.url}")
    
    # 1. Wishlist Check
    tid = 'UPCOMING_249324'
    wish = Wishlist.query.filter_by(title_id=tid).first()
    if wish:
        print(f"Found Wishlist item: {wish.name} ({wish.title_id})")
        print(f"  Release Date: {wish.release_date}")
        print(f"  Icon URL: {wish.icon_url}")
    else:
        print(f"Wishlist item {tid} NOT found!")
        # Try finding by name
        near_mouse = Wishlist.query.filter(Wishlist.name.ilike('%Mouse%')).all()
        for w in near_mouse:
            print(f"Relative found: {w.name} | ID: {w.title_id}")

    # 2. Diablo File Check
    diablo_id = '01001B300B9BE800'
    files = Files.query.filter(Files.filename.ilike(f'%{diablo_id}%')).all()
    print(f"\nFound {len(files)} files for Diablo ({diablo_id})")
    for f in files:
        print(f"ID: {f.id} | Path: {f.filepath} | Identified: {f.identified} | Error: {f.identification_error}")
        if not f.identified:
            print("Force identifying...")
            import titles
            titles.load_titledb()
            # Attempt to identify
            tid, app_type = titles.identify_file(f.filepath)
            print(f"  Identified as: {tid} ({app_type})")
            if tid and tid != f.filename:
                # We should logic here to update the DB if it was a real identification
                pass
