import os
import sys
import sqlite3

dbs = [
    '/Users/fernandosouza/Documents/Projetos/MyFoil/app/config/myfoil.db',
    '/Users/fernandosouza/Documents/Projetos/MyFoil/data/myfoil.db'
]

for db_path in dbs:
    if not os.path.exists(db_path):
        print(f"DB not found: {db_path}")
        continue
    
    print(f"\n=== Checking DB: {db_path} ===")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check Wishlist
    cursor.execute("SELECT id, title_id, name, release_date FROM wishlist WHERE title_id LIKE 'UPCOMING%'")
    rows = cursor.fetchall()
    print(f"Wishlist UPCOMING items: {len(rows)}")
    for r in rows:
        print(f"  {r}")
        
    # Check Diablo File
    diablo_id = '01001B300B9BE800'
    cursor.execute("SELECT id, filename, identified, identification_error FROM files WHERE filename LIKE ?", (f'%{diablo_id}%',))
    files = cursor.fetchall()
    print(f"Diablo files: {len(files)}")
    for f in files:
        print(f"  {f}")
        if f[2] == 0: # Not identified
            print(f"  Force resetting identification for file ID {f[0]}...")
            cursor.execute("UPDATE files SET identified=0, identification_error=NULL WHERE id=?", (f[0],))
            conn.commit()
            print("  Done. App should retry identification on next scan or restart.")

    conn.close()
