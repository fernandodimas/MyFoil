import os
import logging

logger = logging.getLogger("main")


def file_exists_in_db(filepath):
    from db import Files
    return Files.query.filter_by(filepath=filepath).first() is not None


def get_file_from_db(file_id):
    from db import Files
    return Files.query.filter_by(id=file_id).first()


def update_file_path(library, old_path, new_path):
    from db import db, Files, NoResultFound
    try:
        file_entry = Files.query.filter_by(filepath=old_path).one()
        folder = os.path.dirname(new_path)
        if os.path.normpath(library) == os.path.normpath(folder):
            new_folder = ""
        else:
            new_folder = folder.replace(library, "")
            new_folder = "/" + new_folder if not new_folder.startswith("/") else new_folder
        filename = os.path.basename(new_path)
        file_entry.filename = filename
        file_entry.filepath = new_path
        file_entry.folder = new_folder
        db.session.commit()
        logger.info(f"File path updated successfully from {old_path} to {new_path}.")
    except NoResultFound:
        logger.warning(f"No file entry found for the path: {old_path}.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"An error occurred while updating the file path: {str(e)}")


def get_all_titles_from_db():
    from db import Files, to_dict
    results = Files.query.all()
    return [to_dict(r) for r in results]


def get_all_title_files(title_id):
    from db import Files, to_dict
    if not title_id:
        return []
    title_id = title_id.upper()
    results = Files.query.filter_by(title_id=title_id).all()
    return [to_dict(r) for r in results]


def get_all_files_with_identification(identification):
    from db import Files, to_dict
    results = Files.query.filter_by(identification_type=identification).all()
    return [to_dict(r)["filepath"] for r in results]


def get_all_files_without_identification(identification):
    from db import Files, to_dict
    results = Files.query.filter(Files.identification_type != identification).all()
    return [to_dict(r)["filepath"] for r in results]


def get_all_apps():
    from db import db, Apps
    apps_list = [
        {
            "id": app.id,
            "title_id": app.title.title_id if app.title else "UNKNOWN",
            "app_id": app.app_id,
            "app_version": app.app_version,
            "app_type": app.app_type,
            "owned": app.owned,
            "files_info": [{"path": f.filepath, "size": f.size} for f in app.files],
        }
        for app in Apps.query.options(db.joinedload(Apps.title), db.joinedload(Apps.files)).all()
    ]
    return apps_list


def get_all_non_identified_files_from_library(library_id):
    from db import Files
    return Files.query.filter_by(identified=False, library_id=library_id).all()


def get_all_unidentified_files():
    from db import Files
    return Files.query.filter_by(identified=False).all()


def delete_file_from_db_and_disk(file_id):
    from db import db, Files
    file = db.session.get(Files, file_id)
    if not file:
        return False, "File not found in database"
    filepath = file.filepath
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Deleted file from disk: {filepath}")
        db.session.delete(file)
        db.session.commit()
        return True, None
    except Exception as e:
        logger.error(f"Error deleting file {filepath}: {e}")
        return False, str(e)


def get_files_with_identification_from_library(library_id, identification_type):
    from db import Files
    return Files.query.filter_by(library_id=library_id, identification_type=identification_type).all()


def get_filename_identified_files_needing_reidentification(library_id, current_titledb_timestamp):
    from db import db, Files
    if current_titledb_timestamp is None:
        return []
    try:
        ts_float = float(current_titledb_timestamp)
    except (ValueError, TypeError):
        return []
    return (
        Files.query.filter(Files.library_id == library_id, Files.identification_type == "filename")
        .filter(db.or_(Files.titledb_version is None, Files.titledb_version < str(ts_float)))
        .all()
    )


def get_shop_files():
    from db import db, Files, Apps
    shop_files = []
    results = Files.query.options(db.joinedload(Files.apps).joinedload(Apps.title)).all()
    logger.debug(f"get_shop_files: Found {len(results)} total files")

    from titles import get_game_info
    import re

    for file in results:
        if not file.identified:
            continue
        if not file.apps:
            continue
        app = file.apps[0]
        if not app or not app.title:
            continue
        if not file.extension:
            continue

        game_name = app.title.name if (app.title and app.title.name) else ""
        if not game_name:
            try:
                info = get_game_info(app.title.title_id, silent=True)
                if info and info.get("name") and not info["name"].startswith("Unknown"):
                    game_name = info["name"]
                    if app.title and not app.title.name:
                        app.title.name = game_name
                        try:
                            db.session.commit()
                        except Exception:
                            db.session.rollback()
            except Exception as e:
                logger.debug(f"get_shop_files: TitleDB fallback failed for {app.title.title_id}: {e}")

        if game_name:
            game_name = re.sub(r'[\\/*?:"<>|]', "", game_name).strip()
            if game_name:
                game_name = game_name + " "

        if file.multicontent or file.extension.startswith("x"):
            title_id = app.title.title_id
            final_filename = f"{game_name}[{title_id}].{file.extension}"
        else:
            version_val = app.app_version if app.app_version is not None else 0
            final_filename = f"{game_name}[{app.app_id}][v{version_val}].{file.extension}"

        app_name = ""
        try:
            from models.apps import APP_TYPE_DLC
            if app.app_type == APP_TYPE_DLC:
                dlc_info = get_game_info(app.app_id, silent=True)
                if dlc_info and dlc_info.get("name") and not dlc_info["name"].startswith("Unknown"):
                    app_name = dlc_info["name"]
        except Exception:
            pass

        if not app_name:
            app_name = app.title.name or game_name or ""

        shop_files.append({
            "id": file.id,
            "filename": final_filename,
            "size": file.size,
            "title_id": app.title.title_id,
            "app_id": app.app_id,
            "app_name": app_name,
            "app_type": app.app_type,
            "app_version": app.app_version if app.app_version is not None else 0,
        })

    logger.info(f"get_shop_files: Returning {len(shop_files)} shop files")
    return shop_files


def get_libraries():
    from db import Libraries
    return Libraries.query.all()


def get_libraries_path():
    from db import Libraries
    libraries = Libraries.query.all()
    return [l.path for l in libraries]


def add_library(library_path):
    from sqlalchemy import insert
    from db import db, Libraries
    stmt = insert(Libraries).values(path=library_path).on_conflict_do_nothing()
    db.session.execute(stmt)
    db.session.commit()


def delete_library(library):
    from db import db
    if not (isinstance(library, int) or (isinstance(library, str) and library.isdigit())):
        library = get_library_id(library)
    db.session.delete(get_library(library))
    db.session.commit()


def get_library(library_id):
    from db import Libraries
    return Libraries.query.filter_by(id=library_id).first()


def get_library_path(library_id):
    from db import Libraries
    library = Libraries.query.filter_by(id=library_id).first()
    return library.path if library else None


def get_library_id(library_path):
    from db import Libraries
    library = Libraries.query.filter_by(path=library_path).first()
    return library.id if library else None


def get_library_file_paths(library_id):
    from db import Files
    files = Files.query.filter_by(library_id=library_id).all()
    logger.debug(f"get_library_file_paths: Found {len(files)} files for library_id {library_id}")
    return [file.filepath for file in files]


def set_library_scan_time(library_id, scan_time=None):
    from db import db, now_utc
    library = get_library(library_id)
    library.last_scan = scan_time or now_utc()
    db.session.commit()


def get_all_titles():
    from db import Titles
    return Titles.query.all()


def get_all_titles_with_apps():
    from sqlalchemy.orm import joinedload
    from db import Titles, Apps, to_dict, logger as db_logger
    titles = (
        Titles.query.filter(Titles.title_id.isnot(None))
        .options(joinedload(Titles.apps).joinedload(Apps.files), joinedload(Titles.tags))
        .all()
    )
    db_logger.info(f"get_all_titles_with_apps: Found {len(titles)} titles in DB.")

    results = []
    for t in titles:
        file_max_versions = {}
        for a in t.apps:
            v = a.app_version or 0
            for f in a.files:
                current_max = file_max_versions.get(f.id, 0)
                if v > current_max:
                    file_max_versions[f.id] = v

        t_dict = to_dict(t)
        t_dict["apps"] = []
        for a in t.apps:
            a_dict = to_dict(a)
            a_dict["files"] = [f.filepath for f in a.files]
            files_list = []
            for f in a.files:
                has_error = bool(f.identification_error)
                is_identified = f.identified and not has_error
                real_version = file_max_versions.get(f.id, 0)
                files_list.append({
                    "path": f.filepath,
                    "size": f.size,
                    "id": f.id,
                    "error": f.identification_error,
                    "identified": is_identified,
                    "version": real_version,
                })
            a_dict["files_info"] = files_list
            t_dict["apps"].append(a_dict)
        t_dict["tags"] = [tag.name for tag in t.tags]
        results.append(t_dict)
    return results


def get_title(title_id):
    from db import Titles
    return Titles.query.filter_by(title_id=title_id).first()


def get_title_id_db_id(title_id):
    title = get_title(title_id)
    return title.id if title else None


def add_title_id_in_db(title_id, name=None):
    from db import db, Titles, now_utc
    existing_title = Titles.query.filter_by(title_id=title_id).first()
    if not existing_title:
        try:
            new_title = Titles(title_id=title_id, added_at=now_utc(), name=name)
            db.session.add(new_title)
            db.session.flush()
        except Exception:
            db.session.rollback()
            existing_title = Titles.query.filter_by(title_id=title_id).first()
            if existing_title and name and not existing_title.name:
                existing_title.name = name
                db.session.commit()
    elif name and not existing_title.name:
        existing_title.name = name
        db.session.commit()


def backfill_added_at_for_existing_titles():
    from db import db, Titles
    import time
    start = time.time()
    logger.info("Backfilling added_at for existing titles...")
    titles = Titles.query.all()
    updated = 0
    for title in titles:
        if not title.added_at and title.apps:
            earliest_date = None
            for app in title.apps:
                for file in app.files:
                    if file.last_attempt:
                        if earliest_date is None or file.last_attempt < earliest_date:
                            earliest_date = file.last_attempt
            if earliest_date:
                title.added_at = earliest_date
                updated += 1
    if updated > 0:
        db.session.commit()
        logger.info(f"Backfilled added_at for {updated} titles in {(time.time() - start):.2f}s")
    else:
        logger.info("No titles needed backfill for added_at")


def get_all_title_apps(title_id):
    from sqlalchemy.orm import joinedload
    from db import Titles, Apps, to_dict
    title = (
        Titles.query.options(joinedload(Titles.apps).joinedload(Apps.files), joinedload(Titles.tags))
        .filter_by(title_id=title_id).first()
    )
    if not title:
        return []
    tags = [tag.name for tag in title.tags]
    results = []
    for a in title.apps:
        a_dict = to_dict(a)
        a_dict["files_info"] = [{"path": f.filepath, "size": f.size, "id": f.id, "identified": f.identified} for f in a.files]
        a_dict["tags"] = tags
        results.append(a_dict)
    return results


def get_app_by_id_and_version(app_id, app_version):
    from db import Apps
    return Apps.query.filter_by(app_id=app_id, app_version=app_version).first()


def get_app_files(app_id, app_version):
    app = get_app_by_id_and_version(app_id, app_version)
    return [f.id for f in app.files] if app else []


def is_app_owned(app_id, app_version):
    app = get_app_by_id_and_version(app_id, app_version)
    return app.owned if app else False


def add_file_to_app(app_id, app_version, file_id):
    from db import db
    app = get_app_by_id_and_version(app_id, app_version)
    if app:
        file_obj = get_file_from_db(file_id)
        if file_obj and file_obj not in app.files:
            app.files.append(file_obj)
            app.owned = True
            db.session.flush()
            return True
    return False


def remove_file_from_apps(file_id):
    from db import db
    apps_updated = 0
    file_obj = get_file_from_db(file_id)
    if file_obj:
        associated_apps = file_obj.apps
        for app in associated_apps:
            app.files.remove(file_obj)
            app.owned = len(app.files) > 0
            apps_updated += 1
            logger.debug(f"Removed file_id {file_id} from app {app.app_id} v{app.app_version}. Owned: {app.owned}")
        if apps_updated > 0:
            db.session.flush()
    return apps_updated


def has_owned_apps(title_id):
    from db import Apps
    title = get_title(title_id)
    if not title:
        return False
    owned_apps = Apps.query.filter_by(title_id=title.id, owned=True).first()
    return owned_apps is not None


def remove_titles_without_owned_apps():
    from db import db, Titles, Apps
    owned_titles_subquery = db.session.query(Apps.title_id).filter(Apps.owned == True).distinct().subquery()
    titles_to_delete_query = db.session.query(Titles).filter(
        ~Titles.id.in_(db.select(owned_titles_subquery.c.title_id))
    )
    titles_to_delete = [t.id for t in titles_to_delete_query.all()]
    titles_removed = len(titles_to_delete)
    if titles_to_delete:
        logger.info(f"Removing {titles_removed} titles with no owned apps remaining")
        db.session.query(Titles).filter(Titles.id.in_(titles_to_delete)).delete(synchronize_session=False)
        db.session.commit()
    return titles_removed


def delete_files_by_library(library_path):
    from db import db, Files
    success = True
    errors = []
    try:
        files_to_delete = Files.query.filter_by(library=library_path).all()
        total_apps_updated = 0
        for file in files_to_delete:
            apps_updated = remove_file_from_apps(file.id)
            total_apps_updated += apps_updated
        for file in files_to_delete:
            db.session.delete(file)
        db.session.commit()
        logger.info(f"All entries with library '{library_path}' have been deleted.")
        if total_apps_updated > 0:
            logger.info(f"Updated {total_apps_updated} app entries to remove library file references.")
        return success, errors
    except Exception as e:
        db.session.rollback()
        logger.error(f"An error occurred: {e}")
        success = False
        errors.append({"path": "library/paths", "error": f"An error occurred: {e}"})
        return success, errors


def delete_file_by_filepath(filepath):
    from db import db, Files, NoResultFound
    try:
        file_to_delete = Files.query.filter_by(filepath=filepath).one()
        file_id = file_to_delete.id
        apps_updated = remove_file_from_apps(file_id)
        db.session.delete(file_to_delete)
        db.session.commit()
        logger.info(f"File '{filepath}' removed from database.")
        if apps_updated > 0:
            logger.info(f"Updated {apps_updated} app entries to remove file reference.")
    except NoResultFound:
        logger.info(f"File '{filepath}' not present in database.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"An error occurred while removing the file path: {str(e)}")


def remove_missing_files_from_db():
    from db import db, Files
    try:
        files = Files.query.all()
        ids_to_delete = []
        for i, file_entry in enumerate(files):
            if i % 100 == 0:
                try:
                    import gevent
                    gevent.sleep(0)
                except Exception:
                    pass
            if not os.path.exists(file_entry.filepath):
                ids_to_delete.append(file_entry.id)
                logger.info(f"File not found on disk, marking for deletion: {file_entry.filepath}")

        total_apps_updated = 0
        if ids_to_delete:
            for file_id in ids_to_delete:
                apps_updated = remove_file_from_apps(file_id)
                total_apps_updated += apps_updated
            count = Files.query.filter(Files.id.in_(ids_to_delete)).delete(synchronize_session=False)
            db.session.commit()
            logger.info(f"Cleanup done: removed {count} missing files from DB, updated {total_apps_updated} app entries.")
        else:
            logger.debug("No missing files found to cleanup.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"An error occurred while cleaning up missing files: {str(e)}")
