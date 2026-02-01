
import os
import sys

# Add app directory to path
sys.path.append(os.path.join(os.getcwd(), 'app'))

import constants
from db import db, Libraries
from app import app
import state

with app.app_context():
    print(f"MYFOIL_DB: {constants.MYFOIL_DB}")
    print(f"Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    libs = Libraries.query.all()
    print(f"Libraries in DB: {[(l.id, l.path) for l in libs]}")
    
    if state.watcher:
        print(f"Watching directories: {state.watcher.directories}")
    else:
        print("Watcher is None")
