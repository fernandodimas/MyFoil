import sys
import os
from datetime import datetime

# Add app to path
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import create_app
from job_tracker import job_tracker

app = create_app()
with app.app_context():
    jobs = job_tracker.get_all_jobs()
    print(f"Total Jobs (Recent): {len(jobs)}")
    for job in jobs:
        print(f"ID: {job['id']} | Type: {job['type']} | Status: {job['status']} | Progress: {job['progress']['percent']}% | Message: {job['progress']['message']}")
        print(f"  Started at: {job.get('started_at')} | Error: {job.get('error')}")
    
    if not jobs:
        print("No recent jobs found in DB.")
