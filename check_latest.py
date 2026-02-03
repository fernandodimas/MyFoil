import sys
import os

# Add app to sys.path
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import app
from db import db, Files

def check_latest_file():
    with app.app_context():
        # Get 10 most recently added files
        files = Files.query.order_by(Files.id.desc()).limit(10).all()
        print(f"Latest 10 files in DB:")
        for f in files:
            print(f"  ID: {f.id}")
            print(f"  File: {f.filename}")
            print(f"  Identified: {f.identified}")
            # print(f"  Path: {f.filepath}") # path can be long
            print("-" * 20)

if __name__ == "__main__":
    check_latest_file()
