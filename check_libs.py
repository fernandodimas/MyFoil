import sys
import os

# Add app to sys.path
sys.path.append(os.path.join(os.getcwd(), 'app'))

import app
from db import db, Libraries

def list_libraries():
    with app.app.app_context():
        libs = Libraries.query.all()
        print(f"Found {len(libs)} libraries in DB:")
        for lib in libs:
            print(f"  ID: {lib.id}")
            print(f"  Path: {lib.path}")
            print(f"  Exists on disk: {os.path.exists(lib.path)}")
            
            # Check if it has files
            file_count = len(lib.files)
            print(f"  File Count: {file_count}")
            print("-" * 20)

if __name__ == "__main__":
    list_libraries()
