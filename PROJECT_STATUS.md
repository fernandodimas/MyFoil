# Project Status & Roadmap: MyFoil

This document serves as the central hub for the MyFoil project status, outlining completed features, valid optimizations, and a prioritized roadmap for pending tasks.

---

## ✅ Completed Tasks (Detailed Index)

The following core components have been successfully implemented, tested, and integrated.

### 1. TitleDB Source Management (Backend)
- [x] **New Source Manager**: Implemented `TitleDBSourceManager` in `app/titledb_sources.py` to handle multiple sources.
- [x] **Support for Standard & Legacy Sources**:
  - `json` sources (Tinfoil.media, GitHub raw).
  - `zip_legacy` source (Original MyFoil ZIP with `unzip-http` support).
- [x] **Smart Fallback Logic**: `app/titledb.py` logic updated to try sources in priority order until one succeeds.
- [x] **Background Remote Checks**: Asynchronous pre-fetching of "Last Modified" headers to avoid UI freezing.

### 2. API & Integration
- [x] **REST API Endpoints**: Full CRUD support for sources via `app/routes/settings.py`.
  - `GET /api/settings/titledb/sources`
  - `POST /api/settings/titledb/sources` (Add)
  - `PUT /api/settings/titledb/sources` (Update)
  - `DELETE /api/settings/titledb/sources` (Remove)
  - `POST /api/settings/titledb/sources/reorder` (Priority management)
- [x] **Test Coverage**: Created and verified `test_titledb_sources.py` (All 5 tests passing).

### 3. Internationalization (i18n)
- [x] **Translation Strings**: Added support keys for new TitleDB UI elements in `en.json` and `pt_BR.json`:
  - "TitleDB Sources", "Current Active Source", "Priority", "Force TitleDB Update", etc.

### 4. Documentation
- [x] **README Updates**: Updated `README.md` to reflect new features (Multi-source, API usage, JSON downloads).

---

## 🚧 Pending Tasks (Prioritized Roadmap)

The following tasks are pending and prioritized by urgency/impact.

### 🔴 High Priority (Critical for Release)

#### 1. Docker Production & Async Setup (Celery/Redis)
The current `docker-compose.yml` defines the web app but lacks the necessary worker infrastructure for the async tasks defined in `app.py` (Celery).
- **Task**: Update `docker-compose.yml` to include:
  - `redis` service (Broker).
  - `worker` service (Celery worker process for specific queues).
- **Task**: Verify `Dockerfile` builds successfully with the current `requirements.txt`.
- **Reason**: Without this, library scans on large libraries will time out or block the main thread.

#### 2. Frontend Validation (UI/UX)
While the API and Translations are ready, the actual interaction in the browser needs verification to ensure the JavaScript correctly talks to the new endpoints.
- **Task**: Verify "Drag and Drop" or "Up/Down" arrows for source reordering in `settings.html`.
- **Task**: Test the "Add Custom Source" modal handling (Success/Error states).
- **Task**: Verify the "Remote Date" column properly updates via auto-refresh logic.

### 🟡 Medium Priority (Optimization & Cleanup)

#### 3. Codebase Cleanup
Several files appear to be remnants of refactoring or backup processes and should be removed to keep the repository clean.
- **Target Files to Delete**:
  - `app/app_new.py` (Redundant if merged to `app.py`).
  - `app/app.py.backup` (Old backup).
  - `app/fix_indent.py`, `app/fix_alerts.py` (One-off scripts).
  - `test_titledb_sources.py` (After final verification, or move to `tests/`).

#### 4. Legacy ZIP Removal Plan
Now that direct JSON downloads are implemented and faster, we should plan to eventually phase out the `unzip-http` dependency if it proves unstable, keeping it only as a fast-path fallback.

### 🟢 Low Priority (Polish)

#### 5. Documentation Finalization
- **Task**: Remove "Coming Soon" from the Docker section in `README.md` once the build is verified.
- **Task**: Add screenshots of the new TitleDB Settings panel to the README.

---

## 🛠 Suggested Next Steps for Developer

1.  **Execute Cleanup**: Delete the temporary/backup files identified above.
2.  **Fix Docker Compose**: Define the Redis/Celery services to ensure the background jobs (Library Scan, TitleDB Update) work scalably.
3.  **Manual UI Test**: Boot the app and verify the TitleDB Settings page.
