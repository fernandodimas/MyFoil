from app import create_app
from db import db, Files, Apps, Titles
from sqlalchemy import or_

app = create_app()
with app.app_context():
    # List all files that are NOT identified
    unidentified = Files.query.filter(Files.identified == False).all()
    print(f"Total unidentified files: {len(unidentified)}")
    for f in unidentified:
        print(f"ID: {f.id} | Filename: {f.filename} | Error: {f.identification_error}")
    
    # Search specifically for Diablo related files in the DB
    diablo_files = Files.query.filter(Files.filename.ilike('%Diablo%')).all()
    print(f"\nDiablo files in DB: {len(diablo_files)}")
    for f in diablo_files:
        print(f"ID: {f.id} | Filename: {f.filename} | Identified: {f.identified}")
