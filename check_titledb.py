from app import app
from db import TitleDBCache, Titles, db
import os

with app.app_context():
    cache_count = TitleDBCache.query.count()
    titles_count = Titles.query.count()
    print(f"TitleDBCache rows: {cache_count}")
    print(f"Titles rows: {titles_count}")
    
    # Check for US.en.json or similar files in titledb dir
    titledb_dir = "titledb"
    if os.path.exists(titledb_dir):
        files = os.listdir(titledb_dir)
        print(f"Files in titledb/: {files}")
    else:
        print("titledb/ directory does not exist")
