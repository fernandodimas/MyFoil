# MyFoil Administration Scripts

This directory contains automation scripts for managing and deploying MyFoil.

## Scripts Overview

### Deployment & Testing

#### `deploy_phase_2_1.sh` ⭐
Script to apply database migration for Phase 2.1 (Composite Indexes).

Creates backup → Applies migration → Verifies results → Auto-rollback on failure

```bash
# Run inside myfoil container
docker exec -it myfoil bash
cd /app
bash scripts/deploy_phase_2_1.sh
```

**See**: `DEPLOY_GUIDE.md` for detailed instructions.

#### `test_endpoints.sh`
Test all new endpoints from Phases 2.2 & 7.2 (Health checks, pagination, Celery diagnosis).

```bash
# Local testing
./test_endpoints.sh

# Production testing
BASE_URL=http://your-server.com ./test_endpoints.sh
```

---

### Administration

#### `admin/create_admin_local.py`
Create a local admin user via CLI.

#### `admin/list_users.py`
List all users in the database.

#### `admin/update_password.py`
Update password for a user account.

#### `admin/wipe_users.py`
⚠️ **DANGEROUS**: Delete all users from database. Use with caution!

---

### Maintenance

#### `maintenance/add_i_am_future.py`
Add 'i_am_future' title to database for future references.

#### `maintenance/clear_myfoil.py`
Clear MyFoil database records/caches.

#### `maintenance/create_db.py`
Create/initialize database schema.

#### `maintenance/db_dump.py`
Dump database to SQL file.

#### `maintenance/diag_db.py`
Database diagnostic tool - check integrity, stats, etc.

#### `maintenance/manual_scan.py`
Manually trigger a library scan (alternative to UI trigger).

#### `maintenance/reset_db.py`
⚠️ **DANGEROUS**: Reset database to initial state. **ALL DATA LOST**.

#### `maintenance/reset_system.py`
Reset all MyFoil settings to defaults.

---

### Setup

#### `setup/run_postgres.sh`
Setup PostgreSQL database for MyFoil.

#### `setup/setup_postgres.sh`
Additional PostgreSQL configuration and initialization.

---

### Utilities

#### `update_build_version.py`
Update the `BUILD_VERSION` constant in app constants.

---

## Usage Examples

### Deploy Phase 2.1 Migration

```bash
# 1. Enter container
docker exec -it myfoil bash

# 2. Run migration
bash scripts/deploy_phase_2_1.sh

# 3. Verify
flask db current
# Should show: b2c3d4e5f9g1

# 4. Check indexes
sqlite3 app.db "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%';"
```

### Test Endpoints

```bash
# 1. Make executable (if needed)
chmod +x scripts/test_endpoints.sh

# 2. Run tests
./test_endpoints.sh

# 3. View summary
# Total Tests: X
# Passed: X
# Failed: 0
```

### Manual Library Scan

```bash
# Enter container
docker exec -it myfoil bash

# Run scan
python scripts/maintenance/manual_scan.py

# Watch logs
docker logs -f myfoil-worker
```

### Create Admin User

```bash
# Enter container
docker exec -it myfoil bash

# Run script
python scripts/admin/create_admin_local.py

# Follow prompts
```

---

## Important Notes

- ⚠️ **Scripts in `maintenance/` directory are DANGEROUS** and should be used with caution
- **Always backup your database** before running reset/wipe scripts
- **Read the comments in each script** before running
- Some scripts require you to enter the container before use (`docker exec`)
- All bash scripts are executable (run `chmod +x *.sh` if not)

---

## Script Status

| Script | Type | Status | Auto | Docker |
|--------|------|--------|-----:|-------:|
| deploy_phase_2_1.sh | Deployment | ✅ Active | Yes | Yes |
| test_endpoints.sh | Testing | ✅ Active | Yes | Yes |
| create_admin_local.py | Admin | ✅ Active | No | Yes |
| list_users.py | Admin | ✅ Active | No | Yes |
| update_password.py | Admin | ✅ Active | No | Yes |
| wipe_users.py | Admin | ⚠️ Risk | No | Yes |
| clear_myfoil.py | Maintenance | ⚠️ Risk | No | Yes |
| create_db.py | Setup | Setup Only | No | Yes |
| db_dump.py | Utility | ✅ Backup | No | Yes |
| diag_db.py | Utility | ✅ Diag | No | Yes |
| manual_scan.py | Utility | ✅ Manual | No | Yes |
| reset_db.py | Maintenance | ⛔ Destroy | No | Yes |
| reset_system.py | Maintenance | ⛔ Reset | No | Yes |
| run_postgres.sh | Setup | Setup Only | No | Yes |
| setup_postgres.sh | Setup | Initial | No | Yes |
| update_build_version.py | Utility | Manual | No | Yes |

---

## Troubleshooting

### Script fails with permission denied
```bash
# Make executable
chmod +x scripts/*.sh

# Or run with bash
bash scripts/script_name.sh
```

### Script can't find Python modules
```bash
# Ensure you're in correct directory
cd /app

# Or use Python path
PYTHONPATH=/app python scripts/script_name.py
```

### Docker container access
```bash
# Enter container
docker exec -it myfoil bash

# List scripts
ls -la scripts/

# Run script
bash scripts/deploy_phase_2_1.sh
```

---

## Additional Resources

- **Deployment Guide**: `DEPLOY_GUIDE.md`
- **Implementation Summary**: `IMPLEMENTATION_SUMMARY.md`
- **Optimization Details**: `OPTIMIZATION_PHASE_2_1_2_2_7_2.md`
- **Celery Troubleshooting**: `CELERY_TROUBLESHOOTING.md`

---

Last updated: 2026-02-07
MyFoil v2.2.0+
