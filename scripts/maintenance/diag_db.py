
import os
import sys
from flask import Flask

# Add 'app' directory to sys.path
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import create_app
from db import db, Files, Apps, Titles

app = create_app()

def list_titles():
    with app.app_context():
        print("Listing all titles in DB...")
        titles = Titles.query.limit(20).all()
        for t in titles:
            print(f"ID: {t.id}, TitleID: {t.title_id}, Name: {t.name}")
        
        # Now search for those specific ones
        tids = ["0100453019AA8000", "0100965017338000", "01005270232F2000", "0100FA401961E000", "01009A5021534000"]
        for tid in tids:
            # Case insensitive search
            title = Titles.query.filter(Titles.title_id.ilike(f"%{tid}%")).first()
            if title:
                print(f"\nFOUND TITLE: {title.name} ({title.title_id})")
                apps = Apps.query.filter_by(title_id=title.id).all()
                for app_obj in apps:
                    print(f"  App: {app_obj.app_id} (Type: {app_obj.app_type}, Version: {app_obj.app_version})")
                    for f in app_obj.files:
                        print(f"    File: {f.filename}")
                        print(f"      Identified: {f.identified}")
                        print(f"      Error: {f.identification_error}")
            else:
                print(f"\nTitle ID {tid} not found with ilike.")

if __name__ == "__main__":
    list_titles()
