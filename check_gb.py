import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'app'))
from app import app, db
from db import Titles, Apps, Files
with app.app_context():
    tid = "0100C62011050000"
    title = Titles.query.filter_by(title_id=tid).first()
    if title:
        print(f"TITLE: {title.name} ID={title.id} UP_TO_DATE={title.up_to_date}")
        apps = Apps.query.filter_by(title_id=title.id).order_by(Apps.app_version.desc()).all()
        for a in apps:
            if a.owned:
                print(f"  OWNED APP: {a.app_id} v{a.app_version} Type={a.app_type}")
                for f in a.files:
                    print(f"    FILE: {f.filename}")
            else:
                # print(f"  UNOWNED APP: {a.app_id} v{a.app_version}")
                pass
    else:
        print("TITLE NOT FOUND")
