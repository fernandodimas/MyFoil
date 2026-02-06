import sys
import os
import logging

sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import create_app
from db import get_libraries

def check_db_paths():
    app = create_app()
    with app.app_context():
        libraries = get_libraries()
        print(f"Libraries in DB: {len(libraries)}")
        for lib in libraries:
            exists = os.path.exists(lib.path)
            print(f"Library ID: {lib.id} | Path: {lib.path} | Exists on Host: {exists}")
            if exists:
                try:
                    files = os.listdir(lib.path)
                    print(f"  Files/Dirs in root: {len(files)}")
                except:
                    print(f"  Cannot list directory.")

if __name__ == "__main__":
    check_db_paths()
