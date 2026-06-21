import os

from constants import APP_TYPE_BASE, APP_TYPE_UPD, APP_TYPE_DLC
from db import (
    db,
    Files,
    Apps,
    logger,
    get_libraries,
    get_library_id,
    add_library,
    get_all_titles,
    set_library_scan_time,
    remove_file_from_apps,
    log_activity,
    get_file_from_db,
    get_app_by_id_and_version,
    get_all_non_identified_files_from_library,
    get_files_with_identification_from_library,
    get_filename_identified_files_needing_reidentification,
    add_title_id_in_db,
    remove_titles_without_owned_apps,
)
from metrics import files_identified_total
from library.validation import validate_file, cleanup_metadata_files
import titles as titles_lib
from utils import now_utc
from job_tracker import job_tracker
import gevent
from library_decorators import timed_scan


def add_library_complete(app, watcher, path):

    path = path.rstrip("/")
    invalid_reason = validate_library_path(path)
    if invalid_reason:
        return False, invalid_reason
    path_id = add_library(path)
    if path_id:
        try:
            watcher.add_directory(path)
        except Exception as e:
            logger.warning(f"Failed to add watcher: {e}")
        from library.cache import invalidate_library_cache

        invalidate_library_cache()
        return True, "Library path added"
    return False, "Failed to add library path"


def remove_library_complete(app, watcher, path):
    path = path.rstrip("/")
    library = get_library_id(path)
    if library:
        from library.cache import invalidate_library_cache

        invalidate_library_cache()
        watcher.remove_directory(path)
        from settings import delete_library_path_from_settings

        delete_library_path_from_settings(path)
        files = Files.query.filter_by(library_id=library.id).all()
        for f in files:
            remove_file_from_apps(f.id)
            db.session.delete(f)
        db.session.commit()
        remove_titles_without_owned_apps()
        log_activity("library_removed", details={"path": path})
        return True, "Library path removed"
    return False, "Library path not found"


def init_libraries(app, watcher, paths):
    for path in paths:
        path = path.rstrip("/")
        invalid_reason = validate_library_path(path)
        if invalid_reason:
            logger.warning(f"Invalid library path {path}: {invalid_reason}")
            continue
        try:
            path_id = add_library(path)
            if path_id:
                watcher.add_directory(path)
        except Exception as e:
            logger.warning(f"Failed to add library path {path}: {e}")
    logger.info(f"Libraries initialized: {len(paths)} paths")


def validate_library_path(path):
    if not path or not path.strip():
        return "Path is empty"
    if not os.path.exists(path):
        return f"Path does not exist: {path}"
    if not os.path.isdir(path):
        return f"Path is not a directory: {path}"
    return None


def add_files_to_library(library, files):
    library_id, library_path = library

    if not files:
        return [], []

    new_files = []
    updated_files = []

    batch = []
    BATCH_SIZE = 100

    for filepath in files:
        try:
            valid, reason = validate_file(filepath)
            if not valid:
                logger.debug(f"Skipping invalid file {filepath}: {reason}")
                continue

            file_info = titles_lib.get_file_info(filepath)
            if file_info is None:
                continue

            existing_file = get_file_from_db(filepath)
            if existing_file:
                if existing_file.size != file_info.get("size", 0):
                    logger.info(
                        f"File size changed for {filepath}. Marking for re-identification."
                    )
                    existing_file.identified = False
                    existing_file.size = file_info.get("size", 0)
                    updated_files.append(filepath)
            else:
                new_file = Files(
                    library_id=library_id,
                    filepath=filepath,
                    folder=os.path.dirname(filepath),
                    filename=os.path.basename(filepath),
                    extension=file_info.get("extension"),
                    size=file_info.get("size", 0),
                    compressed=file_info.get("compressed", False),
                )
                batch.append(new_file)

            if len(batch) >= BATCH_SIZE:
                db.session.bulk_save_objects(batch)
                db.session.commit()
                batch = []
                if gevent:
                    gevent.sleep(0)

        except Exception as e:
            logger.error(f"Error processing file {filepath}: {e}")

    if batch:
        db.session.bulk_save_objects(batch)
        db.session.commit()

    return new_files, updated_files


@timed_scan
def scan_library_path(library_path, job_id=None):
    from library.generation import post_library_change

    cleanup_metadata_files(library_path)
    library_id = get_library_id(library_path)

    # Register and start job if not provided
    if not job_id:
        job_id = job_tracker.register_job("library_scan", {"library_path": library_path})
        job_tracker.start_job(job_id)

    logger.info(f"Scanning library path {library_path} (library_id={library_id}, job_id={job_id})...")
    if not os.path.isdir(library_path):
        error_msg = f"Path '{library_path}' is not a directory or doesn't exist."
        logger.warning(error_msg)
        from db import log_activity

        log_activity("library_scan_error", details={"path": library_path, "error": error_msg})
        job_tracker.fail_job(job_id, error_msg)
        return

    try:
        # Check permissions
        if not os.access(library_path, os.R_OK):
            logger.warning(f"No read permission for {library_path}")
            from db import log_activity

            log_activity(
                "library_scan_error", details={"path": library_path, "error": "Permission denied (no read access)"}
            )
    except Exception:
        pass

    lib_name = os.path.basename(library_path) or library_path
    job_tracker.update_progress(job_id, 10, message=f"[{lib_name}] Reading disk files...")
    _, files = titles_lib.getDirsAndFiles(library_path)

    if not files:
        logger.warning(f"No files found in {library_path}.")
        from db import log_activity

        log_activity("library_scan_empty", details={"path": library_path})
    else:
        logger.info(f"Found {len(files)} files on disk in {library_path}")

    job_tracker.update_progress(job_id, 20, message=f"[{lib_name}] Comparing with database...")

    # Get all files for this library (path and size) for efficient comparison
    db_files = Files.query.filter_by(library_id=library_id).all()
    db_files_map = {f.filepath: f for f in db_files}
    filepaths_in_library = set(db_files_map.keys())

    # 1. Detect New vs Updated vs Deleted
    new_files = []
    updated_files = []  # Files where size changed
    for i, filepath in enumerate(files):
        # Yield to other greenlets occasionally
        if i % 100 == 0:
            try:
                import gevent

                gevent.sleep(0)
            except Exception:
                pass

        if filepath not in filepaths_in_library:
            new_files.append(filepath)
        else:
            # Check if size changed (indicates replacement)
            try:
                disk_size = os.path.getsize(filepath)
                if disk_size != db_files_map[filepath].size:
                    logger.info(
                        f"File size changed for {filepath} ({db_files_map[filepath].size} -> {disk_size}). Marking for re-identification."
                    )
                    updated_files.append(filepath)
            except OSError:
                continue

    # 1a. Handle Changed Files (Reset identified status)
    if updated_files:
        for filepath in updated_files:
            file_obj = db_files_map[filepath]
            file_obj.size = os.path.getsize(filepath)
            file_obj.identified = False
            file_obj.identification_error = "File size changed, pending re-identification"
        db.session.commit()
        logger.info(f"Reset identification status for {len(updated_files)} changed files")

    # 1b. Add NEW files
    if new_files:
        logger.info(f"Found {len(new_files)} new files to add")
        total_new = len(new_files)
        for n, filepath in enumerate(new_files):
            if n % 10 == 0 or n == total_new - 1:
                progress_msg = f"[{lib_name}] Adding new files: {n + 1}/{total_new}"
                job_tracker.update_progress(job_id, 30 + int((n / total_new) * 20), message=progress_msg)
                gevent.sleep(0)

            add_files_to_library(library_id, [filepath])
            if n % 5 == 0:
                gevent.sleep(0)

    # 2. Remove deleted files
    disk_files_set = set(files)
    deleted_files = [f for f in filepaths_in_library if f not in disk_files_set]

    if deleted_files:
        if job_tracker.is_cancelled(job_id):
            logger.info(f"Job {job_id} was cancelled by user, stopping scan")
            return

        total_del = len(deleted_files)
        for n, filepath in enumerate(deleted_files):
            if job_tracker.is_cancelled(job_id):
                logger.info(f"Job {job_id} was cancelled by user, stopping scan")
                return

            if n % 10 == 0 or n == total_del - 1:
                progress_msg = f"[{lib_name}] Removing deleted files: {n + 1}/{total_del}"
                job_tracker.update_progress(job_id, 60 + int((n / total_del) * 20), message=progress_msg)
                gevent.sleep(0)

            try:
                file_obj = db_files_map[filepath]
                remove_file_from_apps(file_obj.id)
                db.session.delete(file_obj)
            except Exception as e:
                logger.error(f"Error removing deleted file {filepath}: {e}")

            if (n + 1) % 50 == 0:
                db.session.commit()

        db.session.commit()

    set_library_scan_time(library_id)

    # Log summary
    logger.info(
        f"Scan complete for {library_path}: {len(new_files)} added, {len(updated_files)} changed, {len(deleted_files)} removed"
    )

    job_tracker.update_progress(job_id, 90, message=f"[{lib_name}] Finalizing and updating status...")

    if new_files or updated_files or deleted_files:
        logger.info("Triggering post-scan library update to refresh badges and filters")
        post_library_change()

    job_tracker.complete_job(
        job_id,
        {
            "files_added": len(new_files),
            "files_updated": len(updated_files),
            "files_removed": len(deleted_files),
            "total_files": len(files),
        },
    )

    # Log summary
    logger.info(f"Scan complete for {library_path}: {len(new_files)} added, {len(deleted_files)} removed")


def get_files_to_identify(library_id):
    files_to_identify = []
    non_identified = get_all_non_identified_files_from_library(library_id)
    if non_identified:
        files_to_identify.extend(non_identified)

    cache_timestamp = titles_lib.get_titledb_cache_timestamp()
    if cache_timestamp:
        needs_reidentify = get_filename_identified_files_needing_reidentification(
            library_id, cache_timestamp
        )
        if needs_reidentify:
            files_to_identify.extend(needs_reidentify)

    already_identified = get_files_with_identification_from_library(library_id)
    return files_to_identify, already_identified


def identify_single_file(filepath):
    filename = os.path.basename(filepath)

    identification, success, all_contents, error, suggested_name = titles_lib.identify_file(filepath)

    if not success or not all_contents:
        logger.warning(f"Failed to identify {filename}: {error}")
        file_obj = get_file_from_db(filepath)
        if file_obj:
            file_obj.identified = False
            file_obj.identification_type = identification
            file_obj.identification_error = error
            file_obj.last_attempt = now_utc()
            db.session.commit()
            files_identified_total.inc()
        return

    for content in all_contents:
        title_id = content.get("title_id") or content.get("id")
        app_id = content.get("app_id")
        app_type = content.get("type")
        version = content.get("version")

        title_id_db = None
        if title_id:
            title_id_db = add_title_id_in_db(title_id, create=False)
        if not title_id_db and suggested_name:
            title_id_db = add_title_id_in_db(title_id, name=suggested_name)

        app = get_app_by_id_and_version(app_id, version)
        if not app:
            app = Apps(
                app_id=app_id,
                title_id=title_id_db,
                app_type=app_type,
                version=version,
            )
            db.session.add(app)
            db.session.flush()
        else:
            app.title_id = title_id_db or app.title_id

        file_obj = get_file_from_db(filepath)
        if file_obj:
            file_obj.app_id = app.id
            file_obj.identified = True
            file_obj.identification_type = identification
            file_obj.identification_error = ""
            file_obj.last_attempt = now_utc()
            file_obj.titledb_version = str(titles_lib.get_titledb_cache_timestamp() or "")
        else:
            logger.warning(f"File not found in DB: {filepath}")

        db.session.commit()
        files_identified_total.inc()


def identify_library_files(library):
    library_id, library_path = library

    if not library_id:
        logger.warning(f"Skipping identification for library with no ID: {library_path}")
        return

    files_to_identify, already_identified = get_files_to_identify(library_id)

    if already_identified:
        identified_count = len(already_identified)
        logger.info(f"Files identified for library {library_id}: {identified_count}")

    if not files_to_identify:
        return

    logger.info(f"Identifying {len(files_to_identify)} files in library {library_id} ({library_path})")

    filenames = [os.path.basename(f.filepath) for f in files_to_identify]
    for fname in filenames:
        logger.info(f"  {fname}")

    identified = 0
    errors = 0
    pool_size = min(4, len(files_to_identify))
    pool = gevent.threadpool.ThreadPool(pool_size)

    def process_file(file_obj):
        try:
            identify_single_file(file_obj.filepath)
            return True
        except Exception as e:
            logger.error(f"Failed to identify {file_obj.filepath}: {e}")
            return False
        finally:
            file_obj = None

    async_results = []
    for file_obj in files_to_identify:
        async_results.append(pool.spawn(process_file, file_obj))

    gevent.joinall(async_results)
    pool.join()
    pool.kill()

    for ar in async_results:
        if ar.value:
            identified += 1
        else:
            errors += 1

    logger.info(f"Identification complete: {identified} identified, {errors} errors")


def update_or_create_app_and_link_file(app_id, version, app_type, title_id_db, file_obj):
    existing_app = get_app_by_id_and_version(app_id, version)
    if existing_app:
        existing_app.title_id = title_id_db or existing_app.title_id
        app = existing_app
        db.session.flush()
    else:
        app = Apps(
            app_id=app_id,
            title_id=title_id_db,
            app_type=app_type,
            version=version,
        )
        db.session.add(app)
        db.session.flush()

    file_obj.app_id = app.id
    file_obj.identified = True
    file_obj.identification_type = "filename"
    file_obj.identification_error = ""
    file_obj.last_attempt = now_utc()
    file_obj.titledb_version = str(titles_lib.get_titledb_cache_timestamp() or "")

    return app


def add_missing_apps_to_db():
    titles_lib.load_titledb()
    all_titles = get_all_titles()
    if not all_titles:
        return

    for title_id, _ in all_titles.items():
        try:
            existing_base = get_app_by_id_and_version(title_id, None)
            if not existing_base:
                app = Apps(
                    app_id=title_id + "000",
                    title_id=title_id,
                    app_type=APP_TYPE_BASE,
                    version=0,
                )
                db.session.add(app)

            versions = titles_lib.get_all_existing_versions(title_id)
            if versions:
                for v in versions:
                    ver = v.get("version")
                    update_app_id = title_id + "800"
                    existing = get_app_by_id_and_version(update_app_id, ver)
                    if not existing:
                        app = Apps(
                            app_id=update_app_id,
                            title_id=title_id,
                            app_type=APP_TYPE_UPD,
                            version=ver,
                        )
                        db.session.add(app)

            dlcs = titles_lib.get_all_existing_dlc(title_id)
            if dlcs:
                for dlc_id in dlcs:
                    existing = get_app_by_id_and_version(dlc_id, None)
                    if not existing:
                        app = Apps(
                            app_id=dlc_id,
                            title_id=title_id,
                            app_type=APP_TYPE_DLC,
                            version=0,
                        )
                        db.session.add(app)

            db.session.commit()
        except Exception as e:
            logger.error(f"Error adding missing apps for {title_id}: {e}")
            db.session.rollback()


def trigger_library_update_notification():
    from app import socketio

    socketio.emit("library_updated", {"timestamp": now_utc().isoformat()}, namespace="/")


def process_library_identification(app):
    all_libraries = get_libraries()
    for library in all_libraries:
        if library and hasattr(library, "id") and library.id:
            identify_library_files((library.id, library.path))


def reidentify_all_files_job():
    """Re-identify all files from scratch"""
    from job_tracker import job_tracker
    import gevent
    import app
    import datetime
    from db import db, Files, Apps
    from library.cache import invalidate_library_cache
    from library.generation import generate_library

    with app.app_context():
        logger.info("Starting complete re-identification job...")
        job_id = f"reidentify_all_{int(datetime.datetime.now().timestamp())}"
        job_tracker.register_job("reidentify_all", {}, job_id=job_id)
        job_tracker.start_job(job_id)

        try:
            # Step 1: Clear all Apps associations
            logger.info("Clearing all Apps associations...")
            job_tracker.update_progress(job_id, 0, 100, "Clearing database associations...")

            # Clear 'identified' flag on all files.
            stmt = Files.query.update({"identified": False, "identification_error": None, "identification_attempts": 0})
            logger.info(f"Reset {stmt} files to unidentified state.")

            # Delete all apps
            num_apps = Apps.query.delete()
            logger.info(f"Deleted {num_apps} apps records.")

            db.session.commit()

            # Step 3: Re-identify all files
            logger.info("Re-identifying all files...")
            all_files = Files.query.all()
            total = len(all_files)

            if total == 0:
                job_tracker.complete_job(job_id, "No files to identify")
                return True

            for i, file_obj in enumerate(all_files):
                # Calculate progress
                # 5-95% is identification
                progress = 5 + int((i / total) * 90)

                job_tracker.update_progress(job_id, progress, 100, f"Identifying {file_obj.filename} ({i + 1}/{total})")

                identify_single_file(file_obj.filepath)

                # Yield every 5 files to keep system responsive
                if i % 5 == 0:
                    try:
                        import gevent

                        gevent.sleep(0.01)
                    except ImportError:
                        pass

            # Step 4: Regenerate library cache
            logger.info("Regenerating library cache...")
            job_tracker.update_progress(job_id, 98, 100, "Regenerating library cache...")

            invalidate_library_cache()
            generate_library(force=True)

            job_tracker.complete_job(job_id, f"Re-identified {total} files")
            return True

        except Exception as e:
            logger.error(f"Error re-identifying files: {e}")
            job_tracker.fail_job(job_id, str(e))
            return False
