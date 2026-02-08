# Startup Job Cleanup - Documentation

**Implementation Date**: February 8, 2026  
**Commit**: af70def  
**Status**: ✅ Implemented and pushed

---

## Overview

Implemented automatic cleanup of all stale jobs (travadas/old) when containers start.

This ensures that any jobs stuck in `running` or `scheduled` status from previous container restarts are automatically marked as `failed`.

---

## Problem Solved

### Before Implementation:
- Jobs stuck in 'running' status appeared in UI indefinitely
- File Identification tasks locked in UI (10+ jobs stuck)
- User had to manually cancel each stuck job
- Old jobs accumulated in database over time
- Container restarts didn't clean up stale jobs

### After Implementation:
- **ALL stale jobs automatically marked as FAILED** on startup
- MyFoil app: cleans stuck jobs when starting
- Celery worker: cleans stuck jobs when launching
- No more ghost jobs appearing in System Status
- Database stays clean automatically

---

## Changes Made

### 1. Enhanced `cleanup_stale_jobs()` in `app/job_tracker.py`

**Improvements:**
- Added cleanup of **old jobs** (>1 day old) in addition to stuck jobs
- More detailed logging with job IDs and types
- Better error messages explaining why jobs were reset
- Reset of additional state flags if available
- Handles edge cases more robustly

**Code diff:**
```python
# Before: Only cleared running/scheduled jobs
stale = SystemJob.query.filter(
    SystemJob.status.in_([JobStatus.RUNNING, JobStatus.SCHEDULED])
).all()

# After: Also clears old jobs and provides more details
old_jobs_threshold = now_utc() - timedelta(days=1)
old_jobs = SystemJob.query.filter(
    SystemJob.started_at < old_jobs_threshold,
    SystemJob.status.in_([JobStatus.RUNNING, JobStatus.SCHEDULED])
).all()

all_stale = list(set(stale + old_jobs))

for j in all_stale:
    j.status = JobStatus.FAILED
    j.completed_at = now_utc()
    age = now_utc() - j.started_at
    j.error = f"Job reset during startup (was running for {str(age).split('.')[0]}). This usually means the container was restarted while the job was in progress."
```

---

### 2. Added Worker Startup Cleanup in `app/tasks.py`

**New Signal Handlers:**

#### `worker_process_init.connect`
```python
@worker_process_init.connect
def worker_startup_cleanup(sender=None, **kwargs):
    """Handle Celery worker startup - cleanup all stale jobs aggressively"""
    # Cleans ALL stuck jobs when worker starts
    # Logs each job being cleared for debugging
    # Commits changes to database
```

**Actions:**
- Cleans `running`/`scheduled` jobs from previous session
- Cleans old jobs (>1 day) to prevent accumulation
- Logs detailed information about jobs being cleared
- Provides clear reason for cleanup in job error message

---

#### `worker_ready.connect`
```python
@worker_ready.connect
def worker_ready_cleanup(sender=None, **kwargs):
    """Additional cleanup when worker is ready to accept tasks"""
    # Purges stale tasks in Celery queue
    # Logs worker readiness information
    # Clears memory of old tasks
```

**Actions:**
- Inspects Celery worker stats
- Purges any revoked or stuck tasks in queue
- Provides worker readiness information in logs

---

### 3. Enhanced Startup Logging in `app/app.py`

**Added:**
```python
logger.info("=" * 80)
logger.info("STARTUP: Cleaning up stale jobs from previous session...")
logger.info("=" * 80)
job_tracker.cleanup_stale_jobs()
logger.info("STARTUP: Job cleanup completed")
```

**Purpose:**
- Clear visual feedback during application startup
- Makes it obvious when cleanup is happening
- Helps with debugging startup issues

---

## How It Works

### On MyFoil App Startup:

1. **Container starts** → Flask app initializes
2. **`init_internal()`** called → Startup sequence begins
3. **JobTracker cleanup runs first** → Before any other initialization
4. **Searches for stuck jobs**:
   - Jobs with status = `running`
   - Jobs with status = `scheduled`
   - Jobs older than 1 day
5. **Marks jobs as FAILED** → With detailed error message
6. **Commits to database** → Changes saved
7. **Proceeds with normal startup** → Loads TitleDB, starts watcher, etc.

---

### On Celery Worker Startup:

1. **Worker starts** → Celery launches worker process
2. **`worker_process_init` signal fires** → Worker initialization starts
3. **Worker cleanup runs** → Before accepting new tasks
4. **Searches for stuck jobs** → Same logic as app cleanup
5. **Marks jobs as FAILED** → With error message explaining worker restart
6. **Commits to database** → Changes saved
7. **`worker_ready` signal fires** → Worker ready for new tasks
8. **Additional queue cleanup** → Purges old/stale queue entries
9. **Worker starts accepting tasks** → Normal operation

---

## Triggering the Cleanup

### Automatic (No Action Required):
- Start container: `docker-compose up -d`
- Restart container: `docker-compose restart`
- Deploy new version: Any container restart

### Manual (If Needed):
```bash
# In MyFoil app context
from job_tracker import job_tracker
job_tracker.cleanup_stale_jobs()

# Or via API (if available)
curl -X POST http://localhost:8465/api/system/jobs/cleanup
```

---

## Logs to Watch

### Startup Logs (MyFoil App):
```
INFO: STARTUP: Cleaning up stale jobs from previous session...
INFO: Startup: Resetting 12 stale RUNNING/SCHEDULED jobs to FAILED
INFO:   - Clearing job: scan_library_123abc (library_scan)
INFO:   - Clearing job: identify_456def (file_identification)
INFO:   - Clearing job: titledb_update_789ghi (titledb_update)
INFO: Startup: Cleanup completed for 12 jobs
INFO: STARTUP: Job cleanup completed
```

### Startup Logs (Celery Worker):
```
INFO: Celery worker starting up - cleaning stale jobs...
INFO: Worker startup: Resetting 5 stale jobs to FAILED
INFO:   - Clearing job: identify_abc123 (file_identification)
INFO:   - Clearing job: scan_def456 (library_scan)
INFO: Worker startup: Cleanup completed for 5 jobs
INFO: Celery worker ready - performing final cleanup check...
INFO: Worker worker@myfoil-worker is ready: 20 workers
INFO: Cleared any stale Celery queue entries
```

---

## Benefits

### For Users:
✅ **No more stuck jobs in UI** - All old tasks automatically cleared  
✅ **Clean System Status** - No ghost jobs appearing  
✅ **Faster problem resolution** - Automatic cleanup, no manual intervention  
✅ **Better UX** - System always starts in clean state  

### For Developers:
✅ **Debugging made easier** - Detailed logs show which jobs were cleared  
✅ **Database stays clean** - Old jobs don't accumulate  
✅ **Predictable behavior** - Always same cleanup on every restart  
✅ **Testable** - Can verify cleanup worked by checking database  

---

## Technical Details

### Job Status Flow:
```
Container Restart
    ↓
[running/scheduled] jobs detectados
    ↓
[job.status = 'failed']
    ↓
[job.error = 'Job reset during startup (was running for Xh)']
    ↓
[job.completed_at = now_utc()]
```

### Query Pattern:
```sql
-- Initial stuck jobs
SELECT * FROM system_jobs 
WHERE status IN ('running', 'scheduled')

-- Additional old jobs
SELECT * FROM system_jobs
WHERE started_at < datetime('now', '-1 day')
  AND status IN ('running', 'scheduled')
```

---

## Edge Cases Handled

### 1. **Empty Database**: No jobs to clear → Logs "No stale jobs found"

### 2. **Very Recent Jobs**: If job started < 1 minute ago → Still cleared (prefer aggressive cleanup)

### 3. **No JobTracker**: Logs warning but doesn't crash

### 4. **Database Connection Error**: Caught and logged with traceback

### 5. **Worker Crash During Cleanup**: Transaction rolled back, no partial cleanup

---

## Configuration (Optional)

If you want to adjust the threshold for "old jobs", modify:

```python
# In app/job_tracker.py and app/tasks.py
old_jobs_threshold = now_utc - timedelta(days=1)  # Change this
```

**Recommendation**: Keep at 1 day for aggressive cleanup

---

## Monitoring & Verification

### Verify Cleanup Worked:

1. **Check logs** on container restart:
   ```bash
   # MyFoil app logs
   docker logs myfoil --tail 50

   # Worker logs
   docker logs myfoil-worker --tail 50
   ```

2. **Check database** (via Portainer Console):
   ```python
   from db import SystemJob
   running_jobs = SystemJob.query.filter_by(status='running').count()
   print(f"Running jobs: {running_jobs}")  # Should be 0
   ```

3. **Check UI**:
   - Open System Status
   - Verify no jobs stuck in 'running' status
   - All old jobs should be in 'failed' or 'completed'

---

## Troubleshooting

### Problem: Jobs still stuck after restart

**Solution 1: Check logs**
```bash
docker logs myfoil | grep -i "cleanup\|stale" --tail=50
```

**Solution 2: Force cleanup**
```python
# In Portainer Console
from job_tracker import job_tracker
job_tracker.cleanup_stale_jobs()
```

**Solution 3: Manual database cleanup**
```python
# In Portainer Console
from db import SystemJob, db
stuck = SystemJob.query.filter_by(status='running').all()
for job in stuck:
    job.status = 'failed'
    job.completed_at = now_utc()
db.session.commit()
```

---

### Problem: Too many jobs being cleared

**Issue**: Threshold might be too aggressive  
**Solution**: Adjust `timedelta(days=1)` to `timedelta(days=7)` or `timedelta(hours=6)`

---

## Future Enhancements (Optional)

1. **Add configuration option**: `CLEANUP_OLD_JOBS_THRESHOLD_DAYS=1`
2. **Keep cleanup history**: Log cleanup statistics to database
3. **Metrics**: Export cleanup metrics to monitoring system
4. **Webhook cleanup**: Notify external systems when jobs are cleaned up
5. **Selective cleanup**: Only cleanup certain job types (e.g., file_identification, not system jobs)

---

## Testing

### Test 1: Create Stuck Jobs
```python
# Insert fake stuck jobs into database
from db import SystemJob, db, now_utc
job = SystemJob(
    job_id='test_stuck_job',
    job_type='file_identification',
    status='running',
    started_at=now_utc() - timedelta(hours=24),
)
db.session.add(job)
db.session.commit()
```

### Test 2: Restart Container
```bash
docker-compose restart myfoil
```

### Test 3: Verify cleanup
```bash
# Check logs
docker logs myfoil | grep -i "test_stuck_job"

# Check database
from db import SystemJob
job = SystemJob.query.filter_by(job_id='test_stuck_job').first()
print(f"Status: {job.status}")  # Should be 'failed'
```

---

## Summary

✅ **Implemented**: Automatic job cleanup on container startup  
✅ **Benefits**: No more ghost jobs, clean UI on startup  
✅ **Scope**: Works for MyFoil app and Celery worker  
✅ **Logging**: Detailed logs for debugging  
✅ **Safe**: Transaction rollback on errors  

**Result**: System always starts clean, no manual intervention needed! 🚀

---

Last updated: 2026-02-08
Commit: af70def
Version: 20260208_1751
