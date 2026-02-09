# Phase 3.1: db.py Refactoring - Notes and Next Steps

## What Was Done

1. ✅ Created `refactor_db.py` automation script
2. ✅ Generated all 17 model files in `app/models/`
   - files.py
   - titles.py
   - apps.py
   - user.py
   - Libraries.py (already existed)
   - plus 12 more models
3. ✅ Created 17 repository files in `app/repositories/`
   - Each model has a repository with CRUD methods
4. ✅ Created `app/models/__init__.py` and `app/repositories/__init__.py`

## What Was NOT Done

Due to the complexity and potential for breaking existing functionality, the refactoring was **paused** at this stage:

### Incomplete Tasks:
- ❌ Model definitions still exist in `app/db.py` (causing conflicts)
- ❌ Imports NOT updated across the codebase
- ❌ db.py modifications require careful manual review

## Why Paused?

1. **Breaking Change Risk**: Removing models from db.py while keeping them would cause circular import issues
2. **Time Complexity**: Careful refactoring of 1254-line file with 30+ dependencies
3. **Higher ROI**: Options 2 and 3 (Metrics & Monitoring) provide more immediate value

## Recommended Approach for Future Work

### Phase 3.1B: Safe db.py Refactoring

**Step 1: Deprecate Old Classes**
```python
# In db.py, after creating new models:
# Keep model classes but mark as deprecated with deprecation warnings
```

**Step 2: Gradual Migration**
```python
# Update files one by one to use new imports:
from models.files import Files  # instead of from db import *
# Test each file thoroughly before moving to the next
```

**Step 3: Final Cleanup**
```python
# Once all files updated, can safely remove model classes from db.py
# Use deprecation warnings for any remaining direct imports
```

### Alternative Approach: Keep Both

Instead of removing models from db.py, keep them and deprecate:
- New code should import from `app/models/`
- Old code continues to work with `from db import *`
- Gradual migration at own pace
- Zero risk of breaking functionality

## Files Created

**Models (17 files):**
```
app/models/__init__.py
app/models/libraries.py (existed)
app/models/files.py (NEW)
app/models/titles.py (NEW)
app/models/apps.py (NEW)
app/models/user.py (NEW)
app/models/apitoken.py (NEW)
app/models/tag.py (NEW)
app/models/titletag.py (NEW)
app/models/wishlist.py (NEW)
app/models/wishlistignore.py (NEW)
app/models/webhook.py (NEW)
app/models/titlemetadata.py (NEW)
app/models/metadatafetchlog.py (NEW)
app/models/systemjob.py (NEW)
app/models/activitylog.py (NEW)
app/models/titledbcache.py (NEW)
app/models/titledbversions.py (NEW)
app/models/titledbdlcs.py (NEW)
```

**Repositories (17 files):**
```
app/repositories/__init__.py
app/repositories/files_repository.py (NEW)
app/repositories/titles_repository.py (NEW)
app/repositories/apps_repository.py (NEW)
app/repositories/user_repository.py (NEW)
... (one per model)
```

**Automation:**
- `refactor_db.py` - Script to extract models (created successfully)

## Using the Repositories (Optional)

Once ready to use the new repository pattern:

```python
# Old way (still works):
from db import Files
files = Files.query.all()

# New way:
from repositories.files_repository import FilesRepository
files = FilesRepository.get_all()

# Benefits of repositories:
- Isolated database logic
- Easier to test
- Easier to mock in unit tests
- Clear data access layer
```

## Next Steps (When Ready)

1. **Choose Approach**: Deprecation vs Complete Removal
2. **Update Imports Gradually**: File by file, test thoroughly
3. **Use Repositories**: Replace direct model queries with repository calls
4. **Database Sessions**: Ensure proper session management in repositories
5. **Transactions**: Add transaction support to repositories
6. **Testing**: Add unit tests for repositories

## Risk Assessment

**Current Status:** ⚠️ **LOW RISK** (No production impact)
- Old code still works (imports from db.py)
- New model files created but not used yet
- No changes to database schema

**If Proceeding:** ⚠️ **MODERATE RISK**
- Update imports one by one
- Test each file thoroughly
- Use version control to rollback if issues arise

## Timeline Estimate

- Phase 3.1 (This work): 1-2 hours to complete
- Testing and validation: 1 hour
- Total time to safe completion: 2-3 hours

---

**Recommendation:** Complete Phase 3.1 (Metrics & Monitoring) first (more immediate benefit), then return to finish Phase 3.1 when you have dedicated time for careful refactoring.
