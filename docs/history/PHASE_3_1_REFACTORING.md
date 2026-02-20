# Phase 3.1: Database Refactoring Plan

## Status: In Progress - Models Structure Created

## Current Status

### Completed
- ✅ Created `app/models/` directory
- ✅ Created `app/repositories/` directory
- ✅ Created `app/models/__init__.py` with all model exports
- ✅ Created `app/models/libraries.py` (Libraries model)
- ✅ Created `TESTING_GUIDE.md` with endpoint testing instructions
- ✅ Created `test_api_endpoints.py` automated testing script

### In Progress
- 🔄 Creating individual model files (1 of 18)
  - Libraries: ✅ Complete
  - Files: ⏳ In progress
  - Titles: ⏳ Pending
  - Apps: ⏳ Pending
  - TitleDBCache, TitleDBVersions, TitleDBDLCs: ⏳ Pending
  - User, ApiToken: ⏳ Pending
  - Tag, TitleTag: ⏳ Pending
  - Wishlist, WishlistIgnore: ⏳ Pending
  - Webhook: ⏳ Pending
  - TitleMetadata, MetadataFetchLog: ⏳ Pending
  - SystemJob: ⏳ Pending
  - ActivityLog: ⏳ Pending

### Next Steps

#### Immediate (Phase 3.1a)
1. Create remaining 17 model files in `app/models/`
2. Update imports in existing files to use `from models import *`
3. Remove model definitions from `app/db.py`

#### Short Term (Phase 3.1b)
4. Create `app/repositories/library_repository.py`
   - Move library-related queries from db.py
5. Create `app/repositories/title_repository.py`
   - Move title-related queries from db.py
6. Create `app/repositories/file_repository.py`
   - Move file-related queries from db.py

#### Medium Term (Phase 3.1c)
7. Update all other files to import from repositories
8. Remove remaining query functions from db.py
9. Verify all tests pass

#### Long Term (Phase 3.1d)
10. Create `app/db/__init__.py` for initialization
11. Update `app/db.py` to only contain initialization
12. Update imports throughout the application

## Migration Strategy

### Step 1: Create Model Files
```
app/models/
├── __init__.py (Exports all models)
├── libraries.py
├── files.py
├── titles.py
├── apps.py
├── titledb_cache.py
├── users.py
├── tags.py
├── wishlist.py
├── webhooks.py
├── metadata.py
├── jobs.py
└── activity.py
```

### Step 2: Create Repository Files
```
app/repositories/
├── __init__.py (Exports all repository functions)
├── library_repository.py (Library-related queries)
├── title_repository.py (Title-related queries)
├── file_repository.py (File-related queries)
├── app_repository.py (App-related queries)
└── system_repository.py (System/job-related queries)
```

### Step 3: Update Imports
Replace:
```python
from db import Libraries, Files, Titles
```

With:
```python
from models import Libraries, Files, Titles
```

### Step 4: Refactor db.py
Final db.py should only contain:
- Database initialization (db, migrate)
- Alembic configuration functions
- init_db() function
- Maybe utility functions (to_dict)

## Impact Assessment

### Files to Update
Primary imports of models (~50 files):
- app.py
- routes/*.py (~10 files)
- library.py
- tasks.py
- auth.py
- shop.py
- wishlist.py
- Any other file importing from db.py

### Estimated Work
- Creating model files: 2-3 hours
- Creating repository files: 4-6 hours
- Updating imports: 2-3 hours
- Testing and fixes: 2-4 hours

Total: 10-16 hours

## Testing Plan

1. Unit Tests (after each section)
   - Models can be imported
   - Relationships work correctly
   - Database operations work

2. Integration Tests
   - Library scanning works
   - Title identification works
   - API endpoints work

3. Performance Tests
   - No regression in query performance
   - Indexes still work
   - No N+1 queries

## Notes

- This is a breaking change for imports
- Database schema remains unchanged
- All migrations remain valid
- Zero data loss risk
- Can be rolled back by keeping old imports

---

**Last Updated**: 2026-02-09 09:45 UTC
**Build Version**: 20260209_0939
