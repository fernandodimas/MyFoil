# Celery Worker Troubleshooting Guide

## Problem

Full library scan appears in the MyFoil application log but doesn't reach the Celery worker for execution.

## Root Cause Identified

**Duplicate Gevent Monkey Patching**: Both `tasks.py` and `celery_app.py` were calling `monkey.patch_all()`, causing incompatibility issues with Celery's gevent pool.

## Solutions Implemented

### 1. Fixed Duplicate Monkey Patching

**File**: `app/tasks.py`
- Moved `monkey.patch_all()` to the very top of the file, BEFORE any imports
- Removed sys.path.append() that was after the monkey patch

**File**: `app/celery_app.py`
- Removed duplicate `monkey.patch_all()` call
- Added comment noting that monkey patching is done in tasks.py

### 2. Enhanced Logging

**File**: `app/tasks.py`
- Added comprehensive debug logging to `scan_all_libraries_async` function
- Each step now logs its progress for easier debugging

**File**: `app/routes/system.py`
- Enhanced error handling when queuing Celery tasks
- Added task_id to response for tracking
- Added diagnostic endpoint `/api/system/celery/diagnose`

### 3. Created Diagnostic Tools

#### a) Celery Worker Diagnostic Script
```
./diagnose_celery.py
```
Run this inside the worker container to check:
- Redis connection
- Celery broker connection
- Task registration
- Gevent patching status

#### b) Celery Task Test Script
```
./test_celery_task.py
```
Run this to test sending a task and tracking its execution.

#### c) API Diagnostic Endpoint
```
GET /api/system/celery/diagnose
```
Returns detailed diagnostic information via HTTP API.

## How to Use Diagnostic Tools

### Method 1: Inside Worker Container

```bash
# Enter the worker container
docker exec -it myfoil-worker bash

# Run diagnostic
cd /app
python diagnose_celery.py

# Test task execution
python test_celery_task.py
```

### Method 2: From Host Machine

```bash
# Run diagnostic in container
docker exec myfoil-worker python /app/diagnose_celery.py

# Test task from host (requires Redis connection)
docker exec myfoil-worker python /app/test_celery_task.py
```

### Method 3: Via API Endpoint

```bash
# Get Celery diagnostic status
curl http://localhost:8465/api/system/celery/diagnose

# Expected response:
{
  "success": true,
  "diagnosis": {
    "timestamp": "2026-02-07T10:45:00.000000",
    "checks": {
      "celery_enabled": true,
      "redis_connection": "ok",
      "broker_connection": "ok",
      "workers": ["celery@myfoil-worker"],
      "task_registration": {
        "tasks.scan_all_libraries_async": true,
        "tasks.scan_library_async": true
      },
      "total_registered_tasks": 12,
      "active_tasks": 0,
      "queued_tasks": 0
    },
    "overall_status": "healthy"
  }
}
```

## How to Apply Fixes

### Option 1: Rebuild Containers

```bash
# Stop containers
docker-compose down

# Rebuild worker
docker-compose build worker

# Start containers
docker-compose up -d
```

### Option 2: Hot Reload Files (Development)

If running in development with volume mounts:

1. Copy modified files to the container:
```bash
docker cp app/tasks.py myfoil-worker:/app/tasks.py
docker cp app/celery_app.py myfoil-worker:/app/celery_app.py
docker cp app/tasks.py myfoil:/app/tasks.py
docker cp app/celery_app.py myfoil:/app/celery_app.py
docker cp app/routes/system.py myfoil:/app/routes/system.py
```

2. Restart the worker container:
```bash
docker-compose restart worker
```

## Verify Fix

### Step 1: Check Worker Health

```bash
# Run diagnostic
docker exec myfoil-worker python /app/diagnose_celery.py
```

Expected output:
```
✅ Redis connection successful
✅ Celery broker connection successful
✅ tasks.scan_all_libraries_async
✅ tasks.scan_library_async
✅ Gevent socket available
✅ Monkey patching applied
```

### Step 2: Test Task Execution

```bash
# Send a test scan request via API
curl -X POST http://localhost:8465/api/library/scan \
  -H "Content-Type: application/json" \
  -d '{}'
```

Expected response:
```json
{
  "success": true,
  "async": true,
  "task_id": "abc123...",
  "errors": []
}
```

### Step 3: Monitor Task Execution

```bash
# Watch worker logs
docker logs -f myfoil-worker

# Look for:
# "SCAN_ALL_LIBRARIES_TASK_STARTING"
# "App context created successfully"
# "Found X libraries to scan"
# "Processing library 1/X: /path/to/library"
```

### Step 4: Check API Diagnostics

```bash
# Check Celery status
curl http://localhost:8465/api/system/celery/diagnose
```

## Common Issues and Solutions

### Issue 1: Tasks Not Registered

**Problem**: Task names show as NOT REGISTERED in diagnostic

**Solution**:
1. Check that `tasks.py` is importable
2. Verify `include=['tasks']` in celery_app.py
3. Restart the worker container
4. Check for syntax errors in tasks.py

### Issue 2: Worker Not Responding

**Problem**: Workers list is empty in diagnostic

**Solution**:
1. Check if worker container is running: `docker ps`
2. Check worker logs: `docker logs myfoil-worker`
3. Verify Redis is healthy: `docker exec myfoil-redis redis-cli ping`
4. Restart worker: `docker-compose restart worker`

### Issue 3: Task Stuck in PENDING

**Problem**: Task is queued but never executed

**Solution**:
1. Check if worker is busy: Look at queue status API
2. Check worker logs for errors
3. Verify Gevent pool is configured correctly
4. Check if there are too many concurrent tasks

### Issue 4: Monkey Patching Warnings

**Problem**: Gevent warnings in logs

**Solution**: 
The fixes applied should resolve this. Ensure:
1. `tasks.py` does monkey patching FIRST
2. `celery_app.py` does NOT do monkey patching
3. No other files do monkey patching

## Next Steps

After applying the fixes:

1. **Test the scan**:
   ```bash
   curl -X POST http://localhost:8465/api/library/scan -H "Content-Type: application/json"
   ```

2. **Monitor progress**:
   - Open MyFoil UI and check the jobs panel
   - Watch worker logs: `docker logs -f myfoil-worker`

3. **Verify completion**:
   - Check database for new files
   - Verify library is updated in UI

## Additional Resources

- Celery Documentation: https://docs.celeryq.dev/
- Gevent Documentation: https://www.gevent.org/
- Redis Documentation: https://redis.io/docs/

## Support

If issues persist after applying these fixes:

1. Run the diagnostic script and capture output
2. Check worker logs: `docker logs myfoil-worker --tail 100`
3. Check application logs: `docker logs myfoil --tail 100`
4. Open an issue with diagnostic information
