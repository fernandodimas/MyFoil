from app import db
from db import Titles, Apps

titles = Titles.query.all()
print(f"Total Titles: {len(titles)}")
for t in titles[:5]:
    print(f"  {t.title_id}: {t.name}")

gb = Titles.query.filter_by(title_id="0100C62011050000").first()
if gb:
    print(f"Found GB: {gb.name}, up_to_date={gb.up_to_date}")
    apps = Apps.query.filter_by(title_id=gb.id, owned=True).all()
    for a in apps:
        print(f"  Owned App: {a.app_id} v{a.app_version} Type={a.app_type}")
else:
    print("GB not found")
