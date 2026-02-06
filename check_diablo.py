from app import create_app
from db import db, Files, Apps, Titles
from sqlalchemy import or_

app = create_app()
with app.app_context():
    # Search for files containing '01001B300B9BE800'
    query = Files.query.filter(Files.filename.ilike('%01001B300B9BE800%')).all()
    print(f"Found {len(query)} files for 01001B300B9BE800")
    for f in query:
        print(f"ID: {f.id}")
        print(f"Path: {f.filepath}")
        print(f"Identified: {f.identified}")
        print(f"Error: {f.identification_error}")
        print(f"Size: {f.size}")
        if f.apps:
            print(f"Apps linked: {[a.app_id for a in f.apps]}")
        print("-" * 20)
