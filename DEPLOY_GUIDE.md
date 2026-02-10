# Deployment Guide - Phases 1 & 2 Implementation

This guide covers the immediate implementation steps for Performance Optimization Phases 2.1, 2.2, and 7.2.

---

## Prerequisites

- Docker and Docker Compose installed
- MyFoil application running (version 2.2.0+)
- Access to run commands in containers

---

## Step 1: Apply Database Migration (Phase 2.1)

### 1.1 Automatic Application

The migration script will:
- Create a backup of your database
- Apply the composite indexes migration
- Verify all indexes were created
- Rollback on failure

**Option A: Run in Docker container**
```bash
# Enter the myfoil container (not worker)
docker exec -it myfoil bash
cd /app

# Run the migration script
bash scripts/deploy_phase_2_1.sh
```

**Option B: Run on host (development)**
```bash
cd /Users/fernandosouza/Documents/Projetos/MyFoil
bash scripts/deploy_phase_2_1.sh
```

### 1.2 Manual Application

If the script fails, apply manually:

```bash
# Enter myfoil container
docker exec -it myfoil bash

# Check current migration version
flask db current

# Apply migration
flask db upgrade

# Verify indexes were created
flask db heads

# Verify indexes (PostgreSQL)
psql "$DATABASE_URL" -c "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename IN ('files','titles','apps') ORDER BY indexname;"
```

Expected indexes:
- `idx_files_library_id`
- `idx_files_identified`
- `idx_files_size`
- `idx_titles_up_to_date_have_base`
- `idx_titles_have_base`
- `idx_titles_up_to_date`
- `idx_titles_have_base_added_at`
- `idx_apps_title_id_owned`
- `idx_apps_title_id_type_owned`

### 1.3 Rollback (if needed)

```bash
# Downgrade one migration
flask db downgrade

# This will remove all 9 new indexes
```

---

## Step 2: Test New Endpoints (Phase 2.2 & 7.2)

### 2.1 Run Test Script

```bash
# Make test script executable (if not already)
chmod +x scripts/test_endpoints.sh

# Run tests (default: http://localhost:8465)
BASE_URL=http://localhost:8465 scripts/test_endpoints.sh

# Or specify custom URL (if deployed elsewhere)
BASE_URL=http://your-server.com scripts/test_endpoints.sh
```

### 2.2 Manual Testing

#### Health Check Endpoints

```bash
# Comprehensive health check
curl http://localhost:8465/api/health

# Expected response:
{
  "status": "healthy",
  "checks": {
    "timestamp": "2026-02-07T12:00:00.000000",
    "version": "20260207_1129",
    "database": "ok",
    "redis": "ok",
    "celery": "ok (2 workers)",
    "filewatcher": "running"
  }
}

# Readiness probe (critical components only)
curl http://localhost:8465/api/health/ready

# Liveness probe (app is alive)
curl http://localhost:8465/api/health/live
```

#### Celery Diagnosis

```bash
# Check Celery health and task registration
curl http://localhost:8465/api/system/celery/diagnose

# Expected response:
{
  "success": true,
  "diagnosis": {
    "timestamp": "2026-02-07T12:00:00.000000",
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

#### Paginated Library Endpoint

```bash
# Default pagination (page 1, 50 items)
curl "http://localhost:8465/api/library/paged"

# Custom pagination
curl "http://localhost:8465/api/library/paged?page=2&per_page=100"

# Sorting options
curl "http://localhost:8465/api/library/paged?sort=added_at&order=desc"

# Sorting by size
curl "http://localhost:8465/api/library/paged?sort=size&order=asc"
```

#### Search with Pagination

```bash
# Search for games
curl "http://localhost:8465/api/library/search/paged?q=Zelda&page=1&per_page=20"

# Search with filters
curl "http://localhost:8465/api/library/search/paged?q=Mario&owned=true&up_to_date=true"
```

---

## Step 3: Verify Frontend Changes

### 3.1 Check Frontend Updated

The frontend has been updated to use server-side pagination:

- ✅ `app/static/js/index.js` updated with `loadLibraryPaginated()` function
- ✅ Pagination is handled automatically (loads up to 1000 games initially)
- ✅ Infinite scroll still supported via filtered games

### 3.2 Test Frontend

1. **Open MyFoil in browser**: `http://localhost:8465`
2. **Check browser console** (F12) - should see no errors
3. **Refresh library manually** - click refresh button
4. **Check network tab** in developer tools:
   - New requests to `/api/library` (with `page` and `per_page` parameters)
   - Response time should be faster than before
5. **Test searching** - filter by genre, search by name
6. **Test sorting** - sort by different columns

### 3.3 Monitor Performance

Open browser DevTools → Network tab:
1. Filter by "XHR" requests
2. Watch `/api/library` requests
3. Note response times:
   - Before migration: ~2-5s (loading all games)
   - After migration: ~50-200ms (paginated loading)

---

## Step 4: Production Deployment

### 4.1 Deploy with Docker Compose

```bash
# Stop current containers
docker-compose down

# Pull latest code
git pull origin master

# Rebuild images
docker-compose build

# Start containers
docker-compose up -d

# Wait for services to start
sleep 10

# Run migration script inside myfoil container
docker exec -it myfoil bash -c "cd /app && bash scripts/deploy_phase_2_1.sh"

# Test endpoints
BASE_URL=http://localhost:8465 scripts/test_endpoints.sh
```

### 4.2 Deploy to Production Server (Remote)

```bash
# SSH into production server
ssh user@your-server.com

# Navigate to project directory
cd /path/to/MyFoil

# Pull latest changes
git pull origin master

# Rebuild containers
docker-compose down
docker-compose build
docker-compose up -d

# Run migration
docker exec -it myfoil bash -c "cd /app && bash scripts/deploy_phase_2_1.sh"

# Check logs
docker-compose logs -f myfoil
```

---

## Step 5: Monitor and Troubleshoot

### 5.1 Check Application Logs

```bash
# MyFoil main logs
docker logs -f myfoil

# Worker logs
docker logs -f myfoil-worker

# Redis logs (if using)
docker logs -f myfoil-redis

# PostgreSQL logs (if using)
docker logs -f myfoil-postgres
```

### 5.2 Verify Celery Worker Health

```bash
# Run diagnostic (from Step 2.2)
curl http://your-server.com/api/system/celery/diagnose

# Check worker is processing tasks
curl -X POST http://your-server.com/api/library/scan \
  -H "Content-Type: application/json"

# Watch worker logs to see if task is received
docker logs -f myfoil-worker | grep "SCAN_ALL_LIBRARIES"
```

### 5.3 Verify Database Indexes

```bash
# Inside container
docker exec -it myfoil bash

# Check indexes
psql "$DATABASE_URL" -c "SELECT indexname FROM pg_indexes WHERE schemaname='public' AND indexname LIKE 'idx_%' ORDER BY indexname;"
```

---

## Step 6: Performance Monitoring

### 6.1 Monitor Database

The new indexes should significantly improve query performance:

**Queries that should be faster:**
- Stats overview query: 5-10x faster
- Outdated games query: 3-5x faster
- Metadata filtering: 2-3x faster

### 6.2 Monitor API Response Times

Use `curl` with timing:

```bash
# Measure response time
time curl http://localhost:8465/api/library/paged

# Or use Apache Bench for load testing
ab -n 100 -c 10 http://localhost:8465/api/library/paged
```

### 6.3 Monitor Memory Usage

```bash
# Check container resource usage
docker stats

# MyFoil container memory should stay stable with pagination
# Worker memory usage should also improve due to Celery task optimization
```

---

## Troubleshooting

### Issue 1: Migration fails

**Symptoms**: Script exits with error
```
✗ Migration failed!
Attempting to restore from backup...
```

**Solutions**:
1. Check disk space: `df -h`
2. Check database file permissions: `ls -la app.db`
3. Check PostgreSQL client: `psql --version`
4. Try manual upgrade: `flask db upgrade -v debug`

### Issue 2: Indexes not created

**Symptoms**: Test script shows missing indexes

**Check**: Verify migration was applied
```bash
flask db current
# Should show: b2c3d4e5f9g1
```

**Solution**: Re-apply migration
```bash
flask db upgrade b2c3d4e5f9g1
```

### Issue 3: Worker not receiving tasks

**Symptoms**: Scan started but worker logs show nothing

**Check Celery diagnosis**:
```bash
curl http://localhost:8465/api/system/celery/diagnose
```

**Solutions**:
1. Restart worker: `docker-compose restart worker`
2. Check Redis: `docker exec -it myfoil-redis redis-cli ping`
3. Run diagnostic script: `docker exec -it myfoil-worker python /app/diagnose_celery.py`

### Issue 4: Frontend still loads all games

**Symptoms**: Network tab shows large `/api/library` response

**Check**: Browser console for JavaScript errors

**Solution**: 
1. Clear browser cache
2. Hard refresh: `Ctrl+Shift+R` (Cmd+Shift+R on Mac)
3. Verify `index.js` was updated to use `loadLibraryPaginated()`

---

## Success Criteria

You'll know the deployment was successful when:

✅ Migration completed without errors
✅ All 9 indexes present in database
✅ Health check returns "status": "healthy"
✅ Celery diagnosis shows all tasks registered
✅ Paginated library endpoint returns data with pagination metadata
✅ Frontend loads library with pagination parameters
✅ Library refresh is faster (< 500ms for first page)
✅ Worker receives and processes scan tasks properly
✅ No console errors in browser DevTools
✅ Memory usage is stable (no spikes when loading library)

---

## Next Steps

After successful deployment:

1. **Monitor for 24 hours**
   - Watch application logs
   - Monitor response times
   - Check error rates

2. **Analyze performance metrics**
   - Compare pre-deployment vs post-deployment
   - Document improvements
   - Share results with team

3. **Consider Phase 3 optimization**
   - Redis caching for TitleDB
   - Fix remaining N+1 queries
   - Add distributed locks for concurrency

---

## Support

If you encounter issues:

1. Run test script: `scripts/test_endpoints.sh`
2. Check logs: `docker logs myfoil --tail 100`
3. Run Celery diagnostic: `curl /api/system/celery/diagnose`
4. Review troubleshooting section above
5. Open issue on GitHub with diagnostic output

---

## Rollback Plan

If deployment causes issues:

```bash
# 1. Rollback database migration
docker exec -it myfoil bash
flask db downgrade

# 2. Revert code changes
git revert <commit-hash>

# 3. Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d

# 4. Verify application works
curl http://localhost:8465/api/health
```

---

Last updated: 2026-02-07
Build version: 20260207_1129
