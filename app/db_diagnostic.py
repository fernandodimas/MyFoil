import sys
import os
import sqlite3

# Add current directory to path
sys.path.append(os.getcwd())

import app
from db import db, SystemJob, Files
from utils import now_utc

print("Checking database status...")
db_path = "config/myfoil.db" # Standard path based on constants.py (MYFOIL_DB)

try:
    conn = sqlite3.connect(db_path, timeout=1)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    print(f"Journal mode: {cursor.fetchone()[0]}")
    conn.close()
except Exception as e:
    print(f"Error connecting directly to SQLite: {e}")

with app.app_context():
    try:
        running_jobs = SystemJob.query.filter_by(status='running').all()
        print(f"Found {len(running_jobs)} jobs with 'running' status in DB.")
        for job in running_jobs:
            print(f"  - Job {job.job_id} ({job.job_type}): {job.progress_message}")
            
        total_files = Files.query.count()
        print(f"Total files in DB: {total_files}")
        
    except Exception as e:
        print(f"Error querying DB via SQLAlchemy: {e}")
