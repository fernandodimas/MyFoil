import os

try:
    import gevent
except ImportError:
    gevent = None

import titles._state as _state
from titles.utils import format_release_date, robust_json_load, yield_to_event_loop
from constants import APP_TYPE_DLC, TITLEDB_DIR


def get_game_info(title_id, silent=False):
    from db import Titles

    if title_id is None:
        if not silent:
            _state.logger.error("get_game_info called with title_id=None")
        return None

    search_id = str(title_id).upper()

    if search_id in _state._game_info_cache:
        return _state._game_info_cache[search_id]

    res = {
        "name": f"Unknown ({title_id})",
        "bannerUrl": "",
        "iconUrl": "",
        "id": search_id,
        "category": [],
        "release_date": "",
        "size": 0,
        "publisher": "--",
        "intro": "",
        "description": "",
        "nsuid": "",
        "rating": None,
        "ratingContent": [],
        "languages": [],
        "region": "",
        "is_custom": False,
        "screenshots": [],
    }

    if not _state._titles_db:
        from titles.titledb_cache import load_titledb
        load_titledb()

    info = None
    if _state._titles_db:
        info = _state._titles_db.get(search_id)
        if not info:
            info = _state._titles_db.get(search_id.upper()) or _state._titles_db.get(search_id.lower())

        if not info:
            search_id_upper = search_id.upper()
            for data in _state._titles_db.values():
                if not isinstance(data, dict):
                    continue
                if str(data.get("id", "")).upper() == search_id_upper:
                    info = data
                    break

        if info and isinstance(info, dict):
            res.update(
                {
                    "name": info.get("name") or res["name"],
                    "bannerUrl": info.get("bannerUrl") or info.get("banner_url") or "",
                    "iconUrl": info.get("iconUrl") or info.get("icon_url") or "",
                    "category": info.get("category", [])
                    if isinstance(info.get("category"), list)
                    else ([info.get("category")] if info.get("category") else []),
                    "release_date": format_release_date(info.get("releaseDate") or info.get("release_date")),
                    "size": info.get("size") or 0,
                    "publisher": info.get("publisher") or "Nintendo",
                    "intro": info.get("intro") or "",
                    "description": info.get("description") or "",
                    "rating": info.get("rating"),
                    "ratingContent": info.get("ratingContent") or [],
                    "languages": info.get("languages") or [],
                    "region": info.get("region") or "",
                    "nsuid": info.get("nsuid") or info.get("nsuId") or "",
                    "screenshots": info.get("screenshots") or [],
                }
            )

    try:
        db_title = Titles.query.filter_by(title_id=search_id).first()
        if db_title:
            if db_title.is_custom or (db_title.name and ("Unknown" in res["name"] or not info)):
                res["name"] = db_title.name

            if db_title.icon_url:
                res["iconUrl"] = db_title.icon_url
            if db_title.banner_url:
                res["bannerUrl"] = db_title.banner_url

            if db_title.description:
                res["description"] = db_title.description
            if db_title.publisher:
                res["publisher"] = db_title.publisher
            if db_title.release_date:
                res["release_date"] = format_release_date(db_title.release_date)
            if db_title.size:
                res["size"] = db_title.size
            if db_title.nsuid:
                res["nsuid"] = db_title.nsuid
            if db_title.category:
                res["category"] = db_title.category.split(",")
            res["is_custom"] = db_title.is_custom or False

    except Exception as e:
        if not silent:
            _state.logger.error(f"Error merging database info for {search_id}: {e}")

    if not res["iconUrl"] and not search_id.endswith("000"):
        possible_base_ids = [search_id[:-3] + "000"]
        try:
            prefix = search_id[:-3]
            base_prefix = hex(int(prefix, 16) - 1)[2:].upper().rjust(13, "0")
            possible_base_ids.append(base_prefix + "000")
        except (ValueError, TypeError):
            pass

        for bid in possible_base_ids:
            if bid == search_id:
                continue
            base_info = get_game_info(bid, silent=True)
            if base_info and base_info.get("iconUrl") and not base_info["name"].startswith("Unknown"):
                res["iconUrl"] = base_info["iconUrl"]
                res["bannerUrl"] = res["bannerUrl"] or base_info.get("bannerUrl")
                break

    if not res["iconUrl"] and res["bannerUrl"]:
        res["iconUrl"] = res["bannerUrl"]

    name = res.get("name")
    if name:
        for r in [
            " – Nintendo Switch™ 2 Edition",
            " - Nintendo Switch™ 2 Edition",
            " – Nintendo Switch 2 Edition",
            " - Nintendo Switch 2 Edition",
            " Nintendo Switch 2 Edition",
        ]:
            name = name.replace(r, "")
        res["name"] = name.strip()

    _state._game_info_cache[search_id] = res
    return res


def get_update_number(version):
    return int(version) // 65536


def get_game_latest_version(all_existing_versions):
    return max(v["version"] for v in all_existing_versions)


def get_all_existing_versions(titleid):
    if not _state._titles_db_loaded:
        from titles.titledb_cache import load_titledb
        load_titledb()

    if _state._versions_db is None:
        _state.logger.warning("versions_db is not loaded.")
        return []

    if not titleid:
        return []

    titleid = titleid.lower()
    versions_dict = {}

    if _state._versions_db and titleid in _state._versions_db:
        for v_str, release_date in _state._versions_db[titleid].items():
            try:
                versions_dict[int(v_str)] = release_date
            except (ValueError, TypeError):
                continue

    if not versions_dict:
        return []

    return [
        {
            "version": v,
            "update_number": get_update_number(v),
            "release_date": rd,
        }
        for v, rd in sorted(versions_dict.items())
    ]

    return []


def get_all_app_existing_versions(app_id):
    if _state._cnmts_db is None:
        from titles import load_titledb
        load_titledb()
        if _state._cnmts_db is None:
            _state.logger.warning("cnmts_db is not loaded. Call load_titledb first.")
            return None

    if not app_id:
        return None
    app_id = app_id.lower()
    if app_id in _state._cnmts_db:
        versions_from_cnmts_db = _state._cnmts_db[app_id].keys()
        if len(versions_from_cnmts_db):
            return sorted(versions_from_cnmts_db)
        else:
            _state.logger.warning(f"No keys in cnmts.json for app ID: {app_id.upper()}")
            return None
    else:
        return None


def get_app_id_version_from_versions_txt(app_id):
    if _state._versions_txt_db is None:
        from titles import load_titledb
        load_titledb()
        if _state._versions_txt_db is None:
            _state.logger.error("versions_txt_db is not loaded. Call load_titledb first.")
            return None

    if not app_id:
        return None
    app_id = app_id.lower()
    if app_id in _state._versions_txt_db:
        return _state._versions_txt_db[app_id]
    return None


def get_all_existing_dlc(title_id):
    if _state._cnmts_db is None:
        from titles import load_titledb
        load_titledb()
        if _state._cnmts_db is None:
            _state.logger.error("cnmts_db is not loaded. Call load_titledb first.")
            return []

    if not title_id:
        return []

    title_id = title_id.lower()

    dlcs = []
    if _state._dlcs_by_base_id and title_id in _state._dlcs_by_base_id:
        dlcs = list(_state._dlcs_by_base_id[title_id])
    else:
        for app_id, versions in _state._cnmts_db.items():
            if isinstance(versions, dict):
                for version_key, version_description in versions.items():
                    if (
                        version_description.get("titleType") == 130
                        and version_description.get("otherApplicationId") == title_id
                    ):
                        app_id_upper = app_id.upper()
                        if app_id_upper not in dlcs:
                            dlcs.append(app_id_upper)
                        break

    try:
        from db import Apps, Titles

        local_dlcs = (
            Apps.query.join(Titles).filter(Titles.title_id == title_id.upper(), Apps.app_type == APP_TYPE_DLC).all()
        )
        for app in local_dlcs:
            app_id_upper = app.app_id.upper()
            if app_id_upper not in dlcs:
                dlcs.append(app_id_upper)
    except Exception as e:
        _state.logger.warning(f"Failed to load local DLCs for {title_id} from database: {e}")

    filtered_dlcs = []
    for dlc_id in dlcs:
        try:
            info = get_game_info(dlc_id, silent=True)
            if info.get("isDemo") or "demo" in info.get("name", "").lower():
                continue
        except Exception:
            pass
        filtered_dlcs.append(dlc_id)

    return filtered_dlcs


def get_loaded_titles_file():
    try:
        from db import TitleDBCache, db

        with db.session.no_autoflush:
            sources = db.session.query(TitleDBCache.source).distinct().all()

        source_names = [s[0] for s in sources if s[0]]

        if not source_names:
            return "Database (Empty)"

        regional = [
            s
            for s in source_names
            if "titles" not in s and "versions" not in s and "cnmts" not in s and "languages" not in s
        ]
        if regional:
            return ", ".join(sorted(regional))

        return ", ".join(sorted(source_names))
    except Exception as e:
        _state.logger.warning(f"Error getting loaded titles file: {e}")
        return "Database (Error)"


def get_custom_title_info(title_id):
    if not title_id:
        return None
    try:
        custom_path = os.path.join(TITLEDB_DIR, "custom.json")
        if not os.path.exists(custom_path):
            return None

        custom_db = robust_json_load(custom_path) or {}
        return custom_db.get(str(title_id).upper())
    except Exception as e:
        _state.logger.debug(f"Error in get_custom_title_info: {e}")
        return None


def search_titledb_by_name(query):
    if not _state._titles_db:
        return []

    results = []
    query = query.lower()

    for tid, data in _state._titles_db.items():
        if not isinstance(data, dict):
            continue

        name = data.get("name", "")
        if name and query in name.lower():
            results.append(
                {
                    "id": tid,
                    "name": name,
                    "region": data.get("region", "--"),
                    "iconUrl": data.get("iconUrl"),
                    "bannerUrl": data.get("bannerUrl"),
                    "publisher": data.get("publisher"),
                    "description": data.get("description"),
                }
            )
            if len(results) >= 50:
                break

    return results


def save_custom_title_info(title_id, data):
    from db import db, Titles
    import os

    if not title_id or not data:
        return False, "Missing TitleID or Data"

    title_id = str(title_id).upper()
    _state.logger.info(f"Saving custom info for {title_id}...")

    try:
        db_title = Titles.query.filter_by(title_id=title_id).first()
        if not db_title:
            db_title = Titles(title_id=title_id)
            db.session.add(db_title)

        def update_field(field_name, attr_name=None):
            if not attr_name:
                attr_name = field_name
            if field_name in data and data[field_name] is not None:
                setattr(db_title, attr_name, data[field_name])

        update_field("name")
        update_field("description")
        update_field("publisher")
        update_field("iconUrl", "icon_url")
        update_field("bannerUrl", "banner_url")
        update_field("nsuid")

        if "size" in data:
            try:
                db_title.size = int(data["size"])
            except (ValueError, TypeError):
                pass

        cat_data = data.get("category") or data.get("genre")
        if cat_data:
            if isinstance(cat_data, list):
                db_title.category = ",".join([str(c) for c in cat_data if c])
            else:
                db_title.category = str(cat_data)

        rel_date = data.get("releaseDate") or data.get("release_date")
        if rel_date:
            db_title.release_date = str(rel_date)

        db_title.is_custom = True
        db.session.commit()
        _state.logger.info(f"Saved custom info to database for {title_id}")
    except Exception as e:
        _state.logger.error(f"Error saving custom info to DB for {title_id}: {e}")
        db.session.rollback()

    try:
        custom_path = os.path.join(TITLEDB_DIR, "custom.json")
        os.makedirs(os.path.dirname(custom_path), exist_ok=True)
        custom_db = robust_json_load(custom_path) or {}

        save_data = data.copy()
        if "genre" in save_data and "category" not in save_data:
            save_data["category"] = save_data.pop("genre")
        if "release_date" in save_data and "releaseDate" not in save_data:
            save_data["releaseDate"] = save_data.pop("release_date")

        save_data["id"] = title_id

        if title_id in custom_db and isinstance(custom_db[title_id], dict):
            custom_db[title_id].update(save_data)
        else:
            custom_db[title_id] = save_data

        from utils import safe_write_json

        safe_write_json(custom_path, custom_db, indent=4)

        if _state._titles_db is not None:
            if title_id in _state._titles_db:
                if isinstance(_state._titles_db[title_id], dict):
                    _state._titles_db[title_id].update(save_data)
            else:
                _state._titles_db[title_id] = save_data

        return True, None
    except Exception as e:
        _state.logger.error(f"Error saving custom.json for {title_id}: {e}")
        return False, str(e)


def sync_titles_to_db(force=False):
    from db import db, Titles

    if not _state._titles_db:
        _state.logger.warning("sync_titles_to_db: TitleDB not loaded, skipping sync.")
        return

    from flask import has_app_context

    if not has_app_context():
        _state.logger.warning("sync_titles_to_db: No app context, skipping sync.")
        return

    _state.logger.info("Syncing TitleDB metadata to database...")

    try:
        try:
            db_titles = Titles.query.all()
        except Exception as e:
            if "no such column" in str(e).lower():
                _state.logger.warning(
                    "sync_titles_to_db: Database schema is outdated (missing columns). Skipping sync until next restart."
                )
                return
            raise e

        db_titles_map = {t.title_id.upper(): t for t in db_titles if t.title_id}

        updated_count = 0
        for tid, title in db_titles_map.items():
            if tid in _state._titles_db:
                tdb_info = _state._titles_db[tid]

                if not isinstance(tdb_info, dict):
                    continue

                if not title.is_custom:
                    def set_if_not_empty(obj, attr, val):
                        if val is not None and val != "":
                            setattr(obj, attr, val)

                    set_if_not_empty(title, "name", tdb_info.get("name"))
                    set_if_not_empty(title, "description", tdb_info.get("description"))
                    set_if_not_empty(title, "publisher", tdb_info.get("publisher"))

                    icon = tdb_info.get("iconUrl") or tdb_info.get("icon_url")
                    set_if_not_empty(title, "icon_url", icon)

                    banner = tdb_info.get("bannerUrl") or tdb_info.get("banner_url")
                    set_if_not_empty(title, "banner_url", banner)

                    cat = tdb_info.get("category") or tdb_info.get("genre")
                    if cat:
                        title.category = ",".join(cat) if isinstance(cat, list) else str(cat)

                    release = tdb_info.get("releaseDate") or tdb_info.get("release_date")
                    if not release:
                        latest_ver = max(
                            (_state._versions_db.get(tid.lower(), {}) or {}).items(),
                            key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0,
                            default=None,
                        )
                        if latest_ver:
                            release = latest_ver[1] if isinstance(latest_ver[1], str) else ""
                    set_if_not_empty(title, "release_date", format_release_date(release))

                    if tdb_info.get("size"):
                        title.size = tdb_info.get("size")

                    nsuid_val = tdb_info.get("nsuid") or tdb_info.get("nsuId")
                    if nsuid_val:
                        title.nsuid = str(nsuid_val)

                    ss = tdb_info.get("screenshots")
                    if ss and isinstance(ss, list):
                        title.screenshots_json = ss

                    updated_count += 1

                if updated_count % 500 == 0:
                    yield_to_event_loop()

        db.session.commit()
        _state.logger.info(f"Sync complete. Updated {updated_count} titles in database metadata tracker.")
    except Exception as e:
        _state.logger.error(f"Error during TitleDB-to-DB sync: {e}")
        db.session.rollback()
