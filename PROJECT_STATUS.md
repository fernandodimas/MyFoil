# Project Status & Roadmap: MyFoil

This document serves as the central hub for the MyFoil project status, outlining completed features, valid optimizations, and a prioritized roadmap for pending tasks.

---

### ✅ Completed Tasks (Detailed Index)

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

### 5. Game Metadata & Ratings (RAWG & IGDB Integration)
- [x] **Multi-Provider Support**: Integrated both RAWG and IGDB for robust metadata fetching.
- [x] **New Database Fields**: Added support for Metacritic, RAWG ratings, Playtime (story/completionist), and API-sourced genres/screenshots in the `Titles` table.
- [x] **Auto-Migration**: Implemented schema evolution logic in `app/db.py` to seamlessly update existing SQLite databases.
- [x] **Rating Service**: Developed `app/services/rating_service.py` with rate-limiting, OAuth2 (IGDB), and normalized data handling.
- [x] **Async Processing & Scheduling**: Integrated metadata fetching into Celery tasks and added a weekly background refresh job.
- [x] **Docker Infrastructure**: Updated `docker-compose.yml` with Redis and Celery worker for scalable background processing.
- [x] **UI Enhancements**:
  - Integrated ratings and playtime badges in Library Grid and List views.
  - Enhanced Game Details modal with rich stats, screenshots carousel, and manual refresh button.
  - Added "External APIs" tab in Settings to manage RAWG and IGDB credentials.

---

## 🚧 Pending Tasks (Prioritized Roadmap)

The following tasks are pending and prioritized by urgency/impact.

### 🔴 High Priority (Critical for Release)

#### 1. Frontend Validation (UI/UX)
While the API and Translations are ready, the actual interaction in the browser needs verification to ensure the JavaScript correctly talks to the new endpoints.
- [ ] **Task**: Verify "Drag and Drop" or "Up/Down" arrows for source reordering in `settings.html`.
- [ ] **Task**: Test the "Add Custom Source" modal handling (Success/Error states).
- [ ] **Task**: Verify the "Remote Date" column properly updates via auto-refresh logic.
- [ ] **Task**: Test IGDB connection in settings UI.

### 🟡 Medium Priority (Optimization & Cleanup)

#### 2. Codebase Cleanup
Several files appear to be remnants of refactoring or backup processes and should be removed to keep the repository clean.
- [x] **Cleanup executed**: Redundant files removed from `app/`.

#### 3. Legacy ZIP Removal Plan
Now that direct JSON downloads are implemented and faster, we should plan to eventually phase out the `unzip-http` dependency if it proves unstable, keeping it only as a fast-path fallback.

### 🟢 Low Priority (Polish)

#### 4. Documentation Finalization
- [ ] **Task**: Remove "Coming Soon" from the Docker section in `README.md` once the build is verified.
- [ ] **Task**: Add screenshots of the new Settings panels (TitleDB and APIs) to the README.
- [ ] **Task**: Document the API integration features.

---

## 🛠 Suggested Next Steps for Developer

1.  **Manual UI Test**: Boot the app and verify the "External APIs" section in Settings.
2.  **Verify Tasks**: Check Celery logs to ensure metadata fetching is working correctly for multiple games.
3.  **Final Documentation**: Update README.md with the new screenshots.

