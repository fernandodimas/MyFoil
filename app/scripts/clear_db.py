
import os
import sys

# Add the app directory to the path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from constants import MYFOIL_DB
from db import db

def clear_db():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = MYFOIL_DB
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    
    with app.app_context():
        # Register models
        print("Dropping all tables...")
        db.drop_all()
        print("Recreating all tables...")
        db.create_all()
        print("Database cleared successfully!")

if __name__ == "__main__":
    clear_db()
