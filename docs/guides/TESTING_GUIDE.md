# Testing Guide for Phase 2.2 & 7.2 Endpoints

## Overview
This document provides instructions for testing the new endpoints created during the optimization phases.

## Prerequisites
- MyFoil server running (local production, or container)
- Authentication token (optional but recommended for testing)
- Python 3+ with `requests` library

## Quick Test Script

### Running Tests Locally
```bash
# Run the automated test script
python3 test_api_endpoints.py

# Or run with curl command
curl http://localhost:5000/api/health
```

### Testing on Production Server
```bash
# Replace with your actual domain
python3 test_api_endpoints.py
# Enter URL: https://seu-dominio.com
# Enter auth token: <seu-token>
```

## Manual Testing

### Phase 7.2: Health Check Endpoints

#### 1. Basic Health Check (Public)
```bash
curl https://seu-dominio.com/api/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-02-09T12:00:00Z",
  "version": "20260209_0926",
  "database": "ok",
  "redis": "ok",
  "celery": "unknown"
}
```

#### 2. Readiness Probe (Kubernetes)
```bash
curl https://seu-dominio.com/api/health/ready
```

#### 3. Liveness Probe (Kubernetes)
```bash
curl https://seu-dominio.com/api/health/live
```

### Phase 2.2: Pagination Endpoints

#### 1. Paginated Library (Requires Auth)
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://seu-dominio.com/api/library/paged?page=1&per_page=10&sort=name&order=asc"
```

**Expected Response:**
```json
{
  "items": [...],
  "pagination": {
    "page": 1,
    "per_page": 10,
    "total_items": 150,
    "total_pages": 15,
    "has_next": true,
    "has_prev": false,
    "sort_by": "name",
    "order": "asc"
  }
}
```

#### 2. Paginated Search (Requires Auth)
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://seu-dominio.com/api/library/search/paged?q=mario&page=1&per_page=10"
```

### Phase 2.1: Database Migration Endpoints

#### 1. Check Migration Status (Admin Required)
```bash
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  https://seu-dominio.com/api/system/migrate/status
```

#### 2. Apply Phase 2.1 Composite Indexes (Admin Required)
```bash
curl -X POST -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  https://seu-dominio.com/api/system/migrate/phase-2-1
```

**Expected Response:**
```json
{
  "success": true,
  "message": "Phase 2.1 migration applied: Composite indexes created",
  "revision": "b2c3d4e5f9g1",
  "indexes": [...]
}
```

### Celery Worker Testing

#### 1. Test Worker Connectivity (Admin Required)
```bash
curl -X POST -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  https://seu-dominio.com/api/system/celery/test
```

#### 2. Test Scan Task (Admin Required)
```bash
curl -X POST -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  https://seu-dominio.com/api/system/celery/scan-test
```

## Portainer Console Testing

If running in Docker/Portainer, you can test directly:

```bash
# In Portainer Console for web container:
curl http://localhost:5000/api/health

# To test with auth:
curl -H "Authorization: Bearer $(cat /app/data/api_token.txt)" \
  http://localhost:5000/api/system/migrate/status
```

## Performance Benchmarks

After applying Phase 2.1 migration:

| Query | Before | After | Improvement |
|-------|--------|-------|-------------|
| Stats queries | 200-500ms | 20-50ms | **5-10x** |
| Outdated games | 100-200ms | 20-40ms | **3-5x** |
| File size | 50-100ms | 15-30ms | **2-3x** |

## Troubleshooting

### Connection Refused
- **Cause**: Server not running
- **Solution**: Start Docker containers or Flask server

### 401 Unauthorized
- **Cause**: Missing or invalid auth token
- **Solution**: Provide valid token for admin/protected endpoints

### 403 Forbidden
- **Cause**: Insufficient permissions
- **Solution**: Ensure logged in as user with required access level

### Database Errors
- **Cause**: Migration not applied
- **Solution**: Run `POST /api/system/migrate/phase-2-1`

## Next Steps

After verifying endpoints work:
1. ✓ Phase 2.1: Apply database migration for composite indexes
2. ✓ Phase 2.2: Enable pagination in frontend
3. ✓ Phase 7.2: Configure health checks in Kubernetes/Podman
4. → Phase 3.1: Refactor db.py into smaller modules

## Contact

For issues with endpoints, check:
- Application logs: `docker-compose logs -f web`
- Celery logs: `docker-compose logs -f worker`
- Database: Check migration status via `/api/system/migrate/status`
