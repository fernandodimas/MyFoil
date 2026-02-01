
import sys, os
sys.path.append(os.path.join(os.getcwd(), 'app'))
from app import app
from db import db, Libraries, Titles, Files
with app.app_context():
    print(f"Libraries: {Libraries.query.count()}")
    print(f"Titles: {Titles.query.count()}")
    print(f"Files: {Files.query.count()}")
    for l in Libraries.query.all():
        print(f"Library: {l.id} - {l.path}")
