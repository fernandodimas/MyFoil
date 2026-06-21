import os

from constants import APP_TYPE_BASE, APP_TYPE_UPD, APP_TYPE_DLC
from db import (
    db, Files, Apps, Titles, logger, get_all_titles_with_apps, remove_titles_without_owned_apps,
)
from sqlalchemy.orm import joinedload
from models.titlemetadata import TitleMetadata
from library._state import LIBRARY_CACHE
import titles as titles_lib
from utils import format_size_py, now_utc
import gevent
from metrics import library_size_bytes
from utils import debounce


def update_titles():
    # Ensure TitleDB is loaded to avoid clearing up_to_date and complete status flags
    titles_lib.load_titledb()
    try:
        # Remove titles that no longer have any owned apps
        titles_removed = remove_titles_without_owned_apps()
        if titles_removed > 0:
            logger.info(f"Removed {titles_removed} titles with no owned apps.")

        # Auto-heal: Ensure apps with files are marked as owned
        # This fixes cases where files were linked but 'owned' flag wasn't updated due to bugs
        try:
            # FIX: PostgreSQL requires boolean comparison (owned = true), not integer (owned = 1)
            db.session.execute(
                db.text("UPDATE apps SET owned = true WHERE id IN (SELECT app_id FROM app_files) AND owned = false")
            )
            db.session.commit()
        except Exception as e:
            logger.warning(f"Auto-heal owned status failed: {e}")
            db.session.rollback()

        # Optimized query to fetch titles and their apps in fixed number of queries
        titles = Titles.query.options(joinedload(Titles.apps).joinedload(Apps.files)).all()
        for n, title in enumerate(titles):
            # Yield to other gevent co-routines
            import gevent

            gevent.sleep(0)

            have_base = False
            up_to_date = False
            complete = False

            title_id = title.title_id

            if not title_id:
                logger.warning(f"Found Title record with null title_id (ID: {title.id}). Skipping.")
                continue

            # Filter owned apps that actually have files associated
            owned_apps_with_files = [a for a in title.apps if a.owned and len(a.files) > 0]

            # check have_base - look for owned base apps with actual files
            owned_base_apps = [app for app in owned_apps_with_files if app.app_type == APP_TYPE_BASE]
            have_base = len(owned_base_apps) > 0

            owned_versions = []
            for a in owned_apps_with_files:
                try:
                    owned_versions.append(int(a.app_version))
                except (ValueError, TypeError):
                    continue

            max_owned_version = max(owned_versions) if owned_versions else -1

            # Available updates from titledb via versions.json
            available_versions = titles_lib.get_all_existing_versions(title_id)
            max_available_version = max((v["version"] for v in available_versions), default=0)
            
            # check up_to_date - consider current max owned vs max available
            up_to_date = max_owned_version >= max_available_version

            # check complete - check against TitleDB known DLCs
            all_possible_dlc_ids = [d.upper() for d in titles_lib.get_all_existing_dlc(title_id)]
            all_possible_dlc_ids = [d for d in all_possible_dlc_ids if d != title_id.upper()]

            if not all_possible_dlc_ids:
                complete = True
            else:
                owned_dlc_ids = set(
                    [a.app_id.upper() for a in title.apps if a.app_type == APP_TYPE_DLC and a.owned and len(a.files) > 0]
                )
                complete = all(d in owned_dlc_ids for d in all_possible_dlc_ids)

            # Materialized counters (to speed up common filters)
            try:
                # Count owned update apps with files (redundant updates counter)
                # Ignore XCI/XCZ files (cartridge dumps often include updates)
                # CORRECT LOGIC: Redundant means we own an update OLDER than the active one (max_owned_version)
                # CORRECT LOGIC: Redundant = more than 1 owned update FILE (excluding XCI/XCZ bundled updates)
                # Match logic from get_game_info_item
                owned_update_files = []
                for a in title.apps:
                    if (a.app_type == APP_TYPE_UPD or a.app_type == "UPD") and a.owned:
                        for f in a.files:
                            if not f.filepath:
                                continue
                            fpath = f.filepath.lower()
                            # Skip XCI/XCZ as they serve as base+update usually
                            if fpath.endswith((".xci", ".xcz")):
                                continue
                            owned_update_files.append(f.id)
                
                # If we have more than 1 owned update file (NSP/NSZ), we have redundancy
                # The "latest" installed update is one, anything else is redundant.
                title.redundant_updates_count = max(0, len(owned_update_files) - 1)

                # Missing DLCs counter: number of DLCs known in TitleDB that are not owned
                missing_dlcs = 0
                if all_possible_dlc_ids:
                    owned_dlc_ids_upper = owned_dlc_ids
                    missing_dlcs = max(0, len(all_possible_dlc_ids) - len(owned_dlc_ids_upper))
                title.missing_dlcs_count = missing_dlcs
            except Exception:
                # In case the DB model doesn't have these columns yet (pre-migration), skip silently
                pass

            if title.up_to_date != up_to_date:
                logger.info(f"Title {title_id} update status changed: {title.up_to_date} -> {up_to_date}")

            if title.complete != complete:
                logger.info(f"Title {title_id} complete status changed: {title.complete} -> {complete}")

            title.have_base = have_base
            title.up_to_date = up_to_date
            title.complete = complete

            # Set added_at when game is first added to library (first base file found)
            if have_base and not title.added_at:
                # Use the earliest file's last_attempt date as the added_at
                earliest_date = None
                for app in title.apps:
                    for file in app.files:
                        if file.last_attempt:
                            if earliest_date is None or file.last_attempt < earliest_date:
                                earliest_date = file.last_attempt
                title.added_at = earliest_date or now_utc()
                logger.info(f"Setting added_at for title {title_id} to {title.added_at}")

            # Commit every 100 titles to avoid excessive memory use
            if (n + 1) % 100 == 0:
                db.session.commit()

        db.session.commit()

        # Recalculate precomputed per-user flags so they are always in sync with TitleDB
        try:
            from auth import User
            from repositories.titles_repository import TitlesRepository
            users = User.query.all()
            for user in users:
                logger.info(f"Precomputing user_title_flags for user {user.id}...")
                TitlesRepository.precompute_flags_for_user(user.id)
        except Exception as e:
            logger.warning(f"Failed to precompute flags for users: {e}")

        # FIX for Issue #4: Remove orphaned titles at the END of update_titles
        # and invalidate cache if any were removed.
        titles_removed = remove_titles_without_owned_apps()
        if titles_removed > 0:
            logger.info(f"Cleaned up {titles_removed} orphaned titles with no remaining files.")
            # We don't call post_library_change here to avoid infinite recursion if
            # post_library_change calls update_titles, but we do need to invalidate cache.
            with LIBRARY_CACHE.lock:
                LIBRARY_CACHE.data = None
            from library.cache import invalidate_library_cache
            invalidate_library_cache()
    finally:
        # Always unload to free memory resources
        titles_lib.unload_titledb()


def update_single_game_in_cache(title_id):
    """Update a single game in library cache (incremental update)"""

    if not LIBRARY_CACHE.data:
        return False

    try:
        titles_lib.load_titledb()
    except Exception:
        pass

    from db import get_all_titles_with_apps

    all_titles = get_all_titles_with_apps()
    title_data = None
    for t in all_titles:
        if t.title_id == title_id:
            title_data = {"title_id": t.title_id, "apps": []}
            for a in t.apps:
                title_data["apps"].append(
                    {
                        "app_id": a.app_id,
                        "app_type": a.app_type,
                        "app_version": a.app_version,
                        "owned": a.owned,
                        "files_info": [],
                    }
                )
                for f in a.files:
                    title_data["apps"][-1]["files_info"].append(
                        {"id": f.id, "path": f.filepath, "size": f.size, "identified": f.identified}
                    )
            break

    if not title_data:
        return False

    game = get_game_info_item(title_id, title_data)
    if not game:
        return False

    with LIBRARY_CACHE.lock:
        LIBRARY_CACHE.data = [g for g in LIBRARY_CACHE.data if g.get("title_id") != title_id]
        LIBRARY_CACHE.data.append(game)
        LIBRARY_CACHE.data.sort(key=lambda x: x.get("name", "Unrecognized") or "Unrecognized")
        LIBRARY_CACHE.hash = None

    from library.cache import save_library_to_disk
    save_library_to_disk({"hash": None, "library": LIBRARY_CACHE.data})

    try:
        import redis_cache

        if redis_cache.is_cache_enabled():
            redis_cache.invalidate_library_cache()
    except ImportError:
        pass

    logger.info(f"Incremental update completed for title {title_id}")
    return True


def incremental_library_update():
    """Perform incremental library update (only changed titles)"""
    logger.info("Starting incremental library update...")

    from library.cache import detect_changed_titles

    changed_titles = detect_changed_titles(since_seconds=300)

    if not changed_titles:
        logger.info("No changed titles detected, skipping incremental update")
        return True

    updated_count = 0
    for title_id in changed_titles:
        if update_single_game_in_cache(title_id):
            updated_count += 1

    logger.info(f"Incremental update completed: {updated_count}/{len(changed_titles)} titles updated")

    from library.scan import trigger_library_update_notification
    trigger_library_update_notification()

    return True


def get_game_info_item(tid, title_data, ignore_preferences=None):
    """Generate a single game item for the library list"""
    try:
        # All apps for this title (already pre-loaded in title_data['apps'])
        all_title_apps = title_data.get("apps", [])

        # We only show games that have at least one OWNED app in the library
        owned_apps = [a for a in all_title_apps if a.get("owned")]
        if not owned_apps:
            return None

        # Filter: Only show Base Title IDs (ending in 000) as primary entries in the dashboard
        if not str(tid).upper().endswith("000"):
            return None
    except Exception as e:
        logger.error(f"Error in get_game_info_item for {tid}: {e}")
        return None

    # Base info from TitleDB
    info = titles_lib.get_game_info(tid)
    if not info:
        # Fallback 1: Use name from database (could be suggested name from identification)
        db_name = title_data.get("name")
        if db_name and "Unknown" not in db_name:
            display_name = db_name
        else:
            # Fallback 2: find a filename from associated files if possible
            display_name = f"Unknown ({tid})"
            if all_title_apps:
                # Try to find a file from any app associated with this title
                for app_meta in all_title_apps:
                    if app_meta.get("files") and len(app_meta["files"]) > 0:
                        display_name = os.path.basename(app_meta["files"][0]["filepath"])
                        break
        info = {"name": display_name, "iconUrl": "", "publisher": "Unknown"}

    game = info.copy()
    game["title_id"] = tid
    game["id"] = tid  # For display on card as game ID

    # Owned version considers Base and Updates
    owned_versions = [int(a["app_version"] or 0) for a in all_title_apps if a.get("owned")]
    game["owned_version"] = max(owned_versions) if owned_versions else 0
    game["display_version"] = str(game["owned_version"])

    def normalize_date(d):
        if not d:
            return ""
        d = str(d).strip()
        # Handle YYYYMMDD
        if len(d) == 8 and d.isdigit():
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        return d

    # Available versions from versions.json
    available_versions = titles_lib.get_all_existing_versions(tid)
    latest_v = max(available_versions, key=lambda x: x["version"], default=None)
    game["latest_version_available"] = latest_v["version"] if latest_v else 0
    game["latest_release_date"] = normalize_date(latest_v["release_date"]) if latest_v else ""

    # Ensure release_date is consistently available for sorting
    original_release = normalize_date(game.get("release_date") or game.get("releaseDate"))
    game["release_date"] = original_release or game["latest_release_date"] or ""
    game["genre"] = game.get("genre") or game.get("category") or ""

    # Status indicators - only consider as owned if files are actually present
    game["has_base"] = any(
        a["app_type"] == APP_TYPE_BASE and a["owned"] and len(a.get("files_info", [])) > 0 for a in all_title_apps
    )

    # Calculate owned version correctly (only apps with files)
    owned_apps_with_files = [a for a in all_title_apps if a["owned"] and len(a.get("files_info", [])) > 0]
    owned_versions = [int(a["app_version"] or 0) for a in owned_apps_with_files]
    game["owned_version"] = max(owned_versions) if owned_versions else 0
    game["display_version"] = str(game["owned_version"])

    game["has_latest_version"] = game["owned_version"] >= game["latest_version_available"]

    # === Compute non-ignored flags using provided ignore_preferences ===
    try:
        _ignore_prefs = ignore_preferences or {}
        if isinstance(_ignore_prefs, dict) and tid in _ignore_prefs:
            game_ignore = _ignore_prefs.get(tid, {})
        else:
            # Caller may pass already-scoped preferences for this title
            game_ignore = _ignore_prefs if isinstance(_ignore_prefs, dict) else {}

        if isinstance(game_ignore.get("dlcs"), set):
            ignored_dlcs_set = game_ignore.get("dlcs", set())
        else:
            ignored_dlcs_set = set(str(k).upper().strip() for k, v in (game_ignore.get("dlcs", {}) or {}).items() if v)
    except Exception:
        ignored_dlcs_set = set()

    # Determine if ALL possible DLCs are owned
    # Start with TitleDB-known DLCs, but also include any DLC apps present in our DB to be robust
    try:
        titledb_dlcs = [d.upper() for d in titles_lib.get_all_existing_dlc(tid) or []]
    except Exception:
        titledb_dlcs = []

    dlc_apps_seen = set([a["app_id"].upper() for a in all_title_apps if a.get("app_type") == APP_TYPE_DLC])

    all_possible_dlc_ids = sorted(set(titledb_dlcs) | dlc_apps_seen)

    # We only count a DLC as owned if it has files attached
    owned_dlc_ids = set(
        [
            a["app_id"].upper()
            for a in all_title_apps
            if a.get("app_type") == APP_TYPE_DLC and a.get("owned") and len(a.get("files_info", [])) > 0
        ]
    )

    # Filter out self-mapping if it somehow appeared
    all_possible_dlc_ids = [d for d in all_possible_dlc_ids if d != tid.upper()]

    game["has_all_dlcs"] = all(d in owned_dlc_ids for d in all_possible_dlc_ids) if all_possible_dlc_ids else True

    # has_non_ignored_updates: there exists an available version > owned_version that is not owned and not ignored
    has_non_ignored_updates = False
    try:
        if game.get("has_base") and not game.get("has_latest_version"):
            available_versions = titles_lib.get_all_existing_versions(tid) or []
            owned_update_versions = set(
                [
                    int(a["app_version"] or 0)
                    for a in all_title_apps
                    if a.get("app_type") in (APP_TYPE_UPD, "UPD") and a.get("owned")
                ]
            )
            current_owned_version = int(game.get("owned_version") or 0)
            for vinfo in available_versions:
                v = int(vinfo.get("version") or 0)
                if v <= current_owned_version:
                    continue
                # If there's an owned update for this version, skip
                if v in owned_update_versions:
                    continue
                has_non_ignored_updates = True
                break
    except Exception:
        has_non_ignored_updates = False

    game["has_non_ignored_updates"] = has_non_ignored_updates

    # has_non_ignored_dlcs: any DLC in all_possible_dlc_ids that is not owned and not ignored
    has_non_ignored_dlcs = False
    try:
        if game.get("has_base") and all_possible_dlc_ids:
            for d in all_possible_dlc_ids:
                d_up = d.upper()
                if d_up in owned_dlc_ids:
                    continue
                # Normalization happens during set construction
                d_up = d.upper()
                if d_up not in ignored_dlcs_set:
                    has_non_ignored_dlcs = True
                    break
    except Exception:
        has_non_ignored_dlcs = False

    game["has_non_ignored_dlcs"] = has_non_ignored_dlcs

    # Check for redundant updates: more than 1 owned update FILE (excluding XCI/XCZ and errors)
    # "Redundant" means having multiple update files where only the latest version is needed.
    # The base file does NOT count towards redundancy.
    update_files_ids = set()
    updates_info = []

    for a in all_title_apps:
        if a["app_type"] in (APP_TYPE_UPD, "UPD") and a["owned"]:
            for f in a.get("files_info", []):
                # Skip files with explicit errors or missing path
                if f.get("error") or not f.get("path"):
                    continue
                file_id = f.get("id")
                filepath = f.get("path", "").lower()

                if file_id:
                    update_files_ids.add(file_id)
                    updates_info.append(
                        {
                            "id": file_id,
                            "path": filepath,
                            "version": int(a.get("app_version") or 0),
                            "owned": True,
                            "is_xci": filepath.endswith(".xci") or filepath.endswith(".xcz"),
                        }
                    )

    # Refined logic: If we have an XCI/XCZ that contains the update, ignore it for redundancy
    non_xci_updates = [u for u in updates_info if not u["is_xci"]]

    # If we have mixed content (XCI + NSP), only count the independent NSPs
    if len(updates_info) > len(non_xci_updates):
        game["updates_count"] = len(non_xci_updates)
    else:
        game["updates_count"] = len(update_files_ids)

    # Redundant = more than 1 owned update file (base file does NOT count)
    # Skip if title is not recognized
    display_name = title_data.get("name", "")
    if not display_name or "Unknown" in (display_name or ""):
        game["has_redundant_updates"] = False
    else:
        game["has_redundant_updates"] = game["updates_count"] > 1

    # Calculate has_non_ignored_redundant (respect ignore_preferences for redundant updates)
    # Calculate has_non_ignored_redundant (respect ignore_preferences for redundant updates)
    game["has_non_ignored_redundant"] = False
    
    # Expose updates list to game object for frontend and logic below
    # Merge available versions (TitleDB) into updates list for frontend display
    all_updates_list = list(updates_info)
    owned_update_versions = set([int(u.get("version") or 0) for u in updates_info])
    
    for av in available_versions:
        try:
            av_ver = int(av.get("version") or 0)
            if av_ver not in owned_update_versions:
                all_updates_list.append({
                    "version": av_ver,
                    "release_date": av.get("release_date"),
                    "owned": False,
                    "path": None
                })
        except Exception:
            continue
            
    all_updates_list.sort(key=lambda x: int(x.get("version") or 0), reverse=True)
    game["updates"] = all_updates_list

    if game["has_redundant_updates"]:
        try:
            # Redundant Logic: Keep the "best" update (highest version), check if OTHERS are ignored.
            owned_updates = [u for u in game.get("updates", []) if u.get("owned")]

            # Sort by version descending. The first one is our "Active" update.
            owned_updates.sort(key=lambda x: int(x.get("version") or 0), reverse=True)

            if len(owned_updates) > 1:
                game["has_non_ignored_redundant"] = True
        except Exception:
            pass

    game["owned"] = len(owned_apps) > 0

    # Include apps for frontend filtering
    game["apps"] = all_title_apps

    # Determine status color for UI and numeric score for sorting
    # Score: 2 = Complete (Green), 1 = Pending (Orange), 0 = No Base (Red/Orange)
    if not game["has_base"]:
        game["status_color"] = "orange"
        game["status_score"] = 0
    elif not game["has_latest_version"] or not game["has_all_dlcs"]:
        game["status_color"] = "orange"
        game["status_score"] = 1
    else:
        game["status_color"] = "green"
        game["status_score"] = 2

    # Added date from database (when game was first added to library)
    game["added_at"] = title_data.get("added_at")
    if game["added_at"]:
        # Convert datetime to ISO string for JSON serialization
        if hasattr(game["added_at"], "isoformat"):
            game["added_at"] = game["added_at"].isoformat()

    # Tags from Title object
    game["tags"] = title_data.get("tags", [])

    # Screenshots from TitleDB (already available in info from step 1218)
    game["screenshots"] = (info.get("screenshots") or []) if info else []

    # Files and details
    game["base_files"] = []
    base_app_entries = [a for a in all_title_apps if a["app_type"] == APP_TYPE_BASE and a["owned"]]
    for b in base_app_entries:
        if "files_info" in b:
            game["base_files"].extend([f["path"] for f in b["files_info"]])

    game["base_files"] = list(set(game["base_files"]))

    # Calculate total size of owned files
    total_size = 0
    for a in all_title_apps:
        if a.get("owned") and "files_info" in a:
            for f in a["files_info"]:
                total_size += f.get("size", 0)

    game["size"] = total_size
    game["size_formatted"] = format_size_py(total_size)

    # === NEW RATINGS & METADATA ===
    game["metacritic_score"] = title_data.get("metacritic_score")
    game["rawg_rating"] = title_data.get("rawg_rating")
    game["rating_count"] = title_data.get("rating_count")
    game["playtime_main"] = title_data.get("playtime_main")

    # Merge enriched metadata from TitleMetadata table for library cards

    # API Genres and Tags
    remote_meta = TitleMetadata.query.filter_by(title_id=tid).all()
    for meta in remote_meta:
        if meta.rating and not game.get("metacritic_score"):
            game["metacritic_score"] = int(meta.rating)
        if meta.description and (
            not game.get("description") or len(meta.description) > len(game.get("description", ""))
        ):
            game["description"] = meta.description
        if meta.rating and not game.get("rawg_rating"):
            game["rawg_rating"] = meta.rating / 20.0

        # API Genres and Tags
        if meta.genres and isinstance(meta.genres, list):
            if not isinstance(game.get("category"), list):
                game["category"] = []
            existing_cats = set(game["category"])
            for g in meta.genres:
                if g and g not in existing_cats:
                    game["category"].append(g)

        if meta.tags and isinstance(meta.tags, list):
            if not isinstance(game.get("tags"), list):
                game["tags"] = []
            existing_tags = set(game["tags"])
            for t in meta.tags:
                if t and t not in existing_tags:
                    game["tags"].append(t)

    # API Genres and Tags from Title Object (fallback/merged)
    api_genres = title_data.get("genres_json")
    if api_genres and isinstance(api_genres, list):
        if not isinstance(game.get("category"), list):
            game["category"] = []
        existing_cats = set(game["category"])
        for g in api_genres:
            if g and g not in existing_cats:
                game["category"].append(g)

    api_tags = title_data.get("tags_json")
    if api_tags and isinstance(api_tags, list):
        if not isinstance(game.get("tags"), list):
            game["tags"] = []
        existing_tags = set(game["tags"])
        for t in api_tags:
            if t and t not in existing_tags:
                game["tags"].append(t)

    # API Screenshots
    api_screenshots = title_data.get("screenshots_json")
    if api_screenshots and isinstance(api_screenshots, list):
        # Normalize existing screenshots to URLs for comparison
        existing_urls = set()
        current_screenshots = game.get("screenshots") or []
        if isinstance(current_screenshots, list):
            for s in current_screenshots:
                if isinstance(s, dict):
                    existing_urls.add(s.get("url"))
                elif isinstance(s, str):
                    existing_urls.add(s)

        if not isinstance(game.get("screenshots"), list):
            game["screenshots"] = []

        for s in api_screenshots:
            if not s:
                continue
            s_url = s.get("url") if isinstance(s, dict) else s
            if s_url and s_url not in existing_urls:
                game["screenshots"].append(s)

    update_apps = [a for a in all_title_apps if a["app_type"] == APP_TYPE_UPD]
    update_apps_by_version = {}
    for a in update_apps:
        v = int(a.get("app_version") or 0)
        if v not in update_apps_by_version or a.get("owned"):
            update_apps_by_version[v] = a

    version_list = []
    # Include all versions found in versions.json
    for v_info in available_versions:
        v_int = v_info["version"]
        if v_int == 0:
            continue

        upd_app = update_apps_by_version.get(v_int)
        version_list.append(
            {
                "version": v_int,
                "owned": upd_app["owned"] if upd_app else False,
                "release_date": v_info["release_date"] or "Unknown",
                "files": upd_app.get("files", []) if upd_app and upd_app["owned"] else [],
            }
        )

    # Also include any owned updates that might NOT be in versions.json (rare but possible)
    for v_int, upd_app in update_apps_by_version.items():
        if v_int not in [v["version"] for v in version_list] and v_int != 0:
            version_list.append(
                {
                    "version": v_int,
                    "owned": upd_app["owned"],
                    "release_date": "Unknown",
                    "files": upd_app.get("files", []) if upd_app["owned"] else [],
                }
            )

    game["updates"] = sorted(version_list, key=lambda x: x["version"], reverse=True)

    # DLC details for the JSON response
    dlcs_by_id = {}
    for dlc_id in all_possible_dlc_ids:
        # Filter out self-mapping
        if dlc_id == tid.upper():
            continue

        dlcs_by_id[dlc_id] = {
            "app_id": dlc_id,
            "name": titles_lib.get_game_info(dlc_id, silent=True).get("name", f"DLC {dlc_id}"),
            "owned": False,
            "latest_version": 0,
            "owned_version": 0,
        }

    dlc_apps = [a for a in all_title_apps if a["app_type"] == APP_TYPE_DLC]
    for dlc_app in dlc_apps:
        aid = dlc_app["app_id"].upper()
        # Skip base title if it appears as DLC
        if aid == tid.upper():
            continue

        v = int(dlc_app["app_version"] or 0)
        if aid not in dlcs_by_id:
            dlcs_by_id[aid] = {
                "app_id": aid,
                "name": titles_lib.get_game_info(aid, silent=True).get("name", f"DLC {aid}"),
                "owned": False,
                "latest_version": 0,
                "owned_version": 0,
            }

        # Mark as owned only if it has files
        if dlc_app["owned"] and len(dlc_app.get("files_info", [])) > 0:
            dlcs_by_id[aid]["owned"] = True
            dlcs_by_id[aid]["owned_version"] = max(dlcs_by_id[aid]["owned_version"], v)
        dlcs_by_id[aid]["latest_version"] = max(dlcs_by_id[aid]["latest_version"], v)

    game["dlcs"] = sorted(
        [d for d in dlcs_by_id.values() if "demo" not in d["name"].lower()],
        key=lambda x: x["name"]
    )
    return game


def generate_library(force=False):
    """Generate the game library grouped by TitleID, using cached version if unchanged"""

    from library.cache import compute_apps_hash

    current_db_hash = compute_apps_hash()

    if not force:
        with LIBRARY_CACHE.lock:
            # Check if memory cache exists AND matches the current DB state
            if LIBRARY_CACHE.data and LIBRARY_CACHE.hash == current_db_hash:
                return LIBRARY_CACHE.data

            # If not in memory matching DB, try loading from disk and VALIDATE hash
            from library.cache import load_library_from_disk
            saved_library = load_library_from_disk()
            if saved_library and saved_library.get("hash") == current_db_hash:
                LIBRARY_CACHE.data = saved_library["library"]
                LIBRARY_CACHE.hash = current_db_hash
                logger.info("Library loaded from disk cache.")
                return LIBRARY_CACHE.data

            logger.info("Library state changed or disks/DB out of sync, rebuilding cache.")

    logger.info(f"Generating library (force={force})...")
    logger.info("generate_library: Loading TitleDB...")
    titles_lib.load_titledb()
    # Clear in-process TitleDB caches so we reflect newest TitleDB state
    try:
        from library.cache import _clear_titledb_caches
        _clear_titledb_caches()
    except Exception:
        pass
    logger.info("generate_library: TitleDB loaded.")

    # Get all Titles known to the system with their apps and files pre-loaded
    logger.info("generate_library: Fetching titles from DB...")
    all_titles_data = get_all_titles_with_apps()
    logger.info(f"generate_library: Fetched {len(all_titles_data)} titles. Processing...")
    games_info = []


    processed_count = 0
    for idx, title_data in enumerate(all_titles_data):
        game = get_game_info_item(title_data["title_id"], title_data)
        if game:
            games_info.append(game)
            processed_count += 1

        # Yield every 50 games to keep server responsive
        if idx % 50 == 0:
            logger.info(
                f"generate_library: Processed {idx}/{len(all_titles_data)} titles. Found {len(games_info)} games so far."
            )
            gevent.sleep(0)

    logger.info(f"generate_library: Finished processing Titles. Total games found: {len(games_info)}")

    sorted_library = sorted(games_info, key=lambda x: x.get("name", "Unrecognized") or "Unrecognized")

    # Diagnostic: log how many games are missing DLCs and how many have redundant updates
    try:
        missing_dlcs_count = sum(1 for g in games_info if not g.get("has_all_dlcs", True) and g.get("has_base", False))
        redundant_count = sum(1 for g in games_info if g.get("has_redundant_updates", False))
        logger.info(f"Library diagnostic: missing_dlcs={missing_dlcs_count}, redundant_updates={redundant_count}")
    except Exception as e:
        logger.debug(f"Failed to compute library diagnostic counts: {e}")

    library_data = {"hash": current_db_hash, "library": sorted_library}

    from library.cache import save_library_to_disk
    save_library_to_disk(library_data)

    with LIBRARY_CACHE.lock:
        LIBRARY_CACHE.data = sorted_library
        LIBRARY_CACHE.hash = current_db_hash

    titles_lib.identification_in_progress_count -= 1
    titles_lib.unload_titledb()
    # Clear caches after unload as well
    try:
        from library.cache import _clear_titledb_caches
        _clear_titledb_caches()
    except Exception:
        pass

    # Update library size metric
    total_size = sum(g.get("size", 0) for g in games_info)
    library_size_bytes.set(total_size)

    logger.info(f"Generating library done. Found {len(games_info)} games used for response.")

    # Emit notification with game count
    try:
        from app import socketio

        socketio.emit(
            "notification",
            {
                "title": "Library Updated",
                "message": f"Biblioteca atualizada: {len(games_info)} jogos encontrados.",
                "type": "info",
            },
            namespace="/",
        )
    except Exception:
        pass

    if len(games_info) == 0:
        # Diagnostic: Why is it empty?
        count_files = Files.query.count()
        count_titles = Titles.query.count()
        count_apps = Apps.query.count()
        logger.warning(f"Library is empty! DB Stats: Files={count_files}, Titles={count_titles}, Apps={count_apps}")

    return sorted_library


def apply_ignore_preferences_to_game(game: dict, ignore_pref_for_title: dict | None):
    """
    Apply per-title ignore preferences to a serialized game dict.
    This sets/updates the keys:
      - has_non_ignored_updates
      - has_non_ignored_dlcs
      - has_non_ignored_redundant

    The function is defensive and won't raise on malformed input.
    """
    try:
        prefs = ignore_pref_for_title or {}
        ignored_dlcs_map = {k.upper(): v for k, v in (prefs.get("dlcs", {}) or {}).items()}
        ignored_updates_map = {str(k): v for k, v in (prefs.get("updates", {}) or {}).items()}

        # Non-ignored updates
        has_non_ignored_updates = False
        if game.get("has_base") and not game.get("has_latest_version"):
            owned_version = int(game.get("owned_version") or 0)
            # game.updates is expected to be list of {version, owned}
            for u in game.get("updates", []) or []:
                try:
                    v = int(u.get("version") or 0)
                except Exception:
                    continue
                if v > owned_version and not u.get("owned") and not ignored_updates_map.get(str(v)):
                    has_non_ignored_updates = True
                    break

        game["has_non_ignored_updates"] = has_non_ignored_updates

        # Non-ignored DLCs
        has_non_ignored_dlcs = False
        if game.get("has_base"):
            # all possible DLC ids may be available as 'dlcs' list (with app_id and owned)
            dlcs_list = game.get("dlcs") or []
            for d in dlcs_list:
                app_id = d.get("app_id") if isinstance(d, dict) else (d or "")
                app_id_up = str(app_id).upper()
                owned = bool(d.get("owned")) if isinstance(d, dict) else False
                if owned:
                    continue
                if not ignored_dlcs_map.get(app_id_up):
                    has_non_ignored_dlcs = True
                    break

        game["has_non_ignored_dlcs"] = has_non_ignored_dlcs

        # Non-ignored redundant updates: check if there are owned updates with versions
        # LOWER than the max owned version that are NOT ignored.
        # Redundancy = having multiple owned update files (the older ones are redundant).
        has_non_ignored_redundant = False
        if game.get("has_redundant_updates"):
            owned_updates = sorted(
                [u for u in (game.get("updates", []) or []) if u.get("owned")],
                key=lambda x: int(x.get("version") or 0),
                reverse=True,
            )
            if len(owned_updates) > 1:
                # The first (highest version) is the "active" update.
                # All subsequent ones are redundant candidates.
                for cand in owned_updates[1:]:
                    try:
                        c_ver = str(int(cand.get("version") or 0))
                    except Exception:
                        continue
                    if not ignored_updates_map.get(c_ver):
                        has_non_ignored_redundant = True
                        break
        game["has_non_ignored_redundant"] = has_non_ignored_redundant

    except Exception:
        # Be defensive: ensure keys exist
        game.setdefault("has_non_ignored_updates", False)
        game.setdefault("has_non_ignored_dlcs", False)
        game.setdefault("has_non_ignored_redundant", False)

    return game


@debounce(10)  # Wait 10s after last change before regenerating
def post_library_change():
    """Called after library changes to update titles and regenerate library cache (DEBOUNCED)"""

    def _do_post_library_change():
        from app import create_app

        # Use minimal app to avoid side effects (watchers, threads) in background task
        app = create_app(minimal=True)

        with app.app_context():

            logger.info("Post-library change: updating titles and cache")

            try:
                # 1. Invalidate in-memory cache FIRST
                with LIBRARY_CACHE.lock:
                    LIBRARY_CACHE.data = None

                # 2. Delete disk cache
                from library.cache import invalidate_library_cache
                invalidate_library_cache()

                # 2.5. Invalidate Redis cache (Phase 4.1)
                try:
                    import redis_cache

                    if redis_cache.is_cache_enabled():
                        redis_cache.invalidate_library_cache()
                        logger.info("Redis library cache invalidated")
                except ImportError:
                    pass

                # 3. Update titles with new files
                # This is critical for updating 'up_to_date' and 'complete' status flags
                # which control the badges (UPDATE, DLC) and filters
                update_titles()

                # 4. Regenerate library cache (force=False)
                # We use force=False to allow it to skip if hash matches (safety check)
                gevent.sleep(0)
                generate_library(force=False)

                # 5. Notify frontend via WebSocket
                from library.scan import trigger_library_update_notification
                trigger_library_update_notification()

                logger.info("Library cache regenerated successfully")
            except Exception as e:
                logger.error(f"Error in post_library_change: {e}")
                import traceback

                traceback.print_exc()

            titles_lib.unload_titledb()

    # Run in background so it doesn't block the scan job completion
    gevent.spawn(_do_post_library_change)


def version_to_string(version_num):
    """
    Convert version number to human-readable string format.

    Args:
        version_num: Integer version number (e.g., 131072)

    Returns:
        String in format "major.minor.patch" (e.g., "2.0.0")
    """
    if not version_num or version_num == 0:
        return "0.0.0"

    major = (version_num >> 26) & 0x3F
    minor = (version_num >> 20) & 0x3F
    patch = (version_num >> 16) & 0xF
    return f"{major}.{minor}.{patch}"


def get_pending_update_info(title_id):
    """
    Get information about the latest available update for a game.

    Args:
        title_id: Game title ID (hex format)

    Returns:
        Dictionary with version info, or None if no updates available:
        {
            "version": 196608,
            "version_string": "3.0.0",
            "update_id": "010012345ABC800",
            "release_date": "2021-11-04"
        }
    """
    import titles as titles_lib

    try:
        # Get all available versions from TitleDB
        available_versions = titles_lib.get_all_existing_versions(title_id)

        if not available_versions:
            return None

        # Sort by version number (descending) to get latest
        sorted_versions = sorted(available_versions, key=lambda v: v.get("version", 0), reverse=True)
        latest = sorted_versions[0]

        # Calculate update app ID (title_id with 800 suffix for updates)
        # Remove trailing zeros and add '800'
        base_id = title_id.upper().rstrip("0")
        update_id = base_id + "800"

        # Convert version number to string (e.g., 131072 -> "2.0.0")
        version_string = version_to_string(latest.get("version", 0))

        return {
            "version": latest.get("version", 0),
            "version_string": version_string,
            "update_id": update_id,
            "release_date": latest.get("releaseDate") or latest.get("release_date") or "Unknown",
        }
    except Exception as e:
        logger.error(f"Error getting pending update info for {title_id}: {e}")
        return None
