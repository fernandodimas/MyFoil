import hashlib
import json
import os
from constants import APP_TYPE_BASE, APP_TYPE_UPD, APP_TYPE_DLC, LIBRARY_CACHE_FILE, ALLOWED_EXTENSIONS, TITLEDB_DIR
from db import (
    db, Files, Apps, Titles, Libraries, logger, joinedload, Tag, app_files,
    get_libraries, get_all_titles_with_apps, get_all_apps, get_all_titles,
    get_library_id, get_library_file_paths, remove_file_from_apps,
    log_activity, get_file_from_db, get_all_non_identified_files_from_library,
    get_files_with_identification_from_library, get_filename_identified_files_needing_reidentification,
    add_library, get_library_path, set_library_scan_time, get_title,
    get_title_id_db_id, add_title_id_in_db, get_all_title_apps,
    get_app_by_id_and_version, remove_titles_without_owned_apps
)
from metrics import FILES_IDENTIFIED, IDENTIFICATION_DURATION, LIBRARY_SIZE
import titles as titles_lib
import datetime
from pathlib import Path
from utils import format_size_py, now_utc, ensure_utc, safe_write_json
import threading
from job_tracker import job_tracker
import gevent

# Session-level cache
_LIBRARY_CACHE = None
_CACHE_LOCK = threading.Lock()

ALLOWED_EXTENSIONS = {".nsp", ".nsz", ".xci", ".xcz"}
MAX_FILE_SIZE = 50 * 1024 * 1024 * 1024  # 50GB


def validate_file(filepath):
    """
    Validate file before processing.
    Checks extension, size, symlinks, and basic header for Switch files.
    """
    path = Path(filepath)

    # 1. Check extension
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Extensão não permitida: {path.suffix}")

    # 2. Check existence and size
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")

    size = path.stat().st_size
    if size == 0:
        raise ValueError("Arquivo vazio")
    if size > MAX_FILE_SIZE:
        raise ValueError("Arquivo excede limite de tamanho (50GB)")

    # 3. Check for malicious symlinks
    if path.is_symlink():
        # Ensure it resolves within a allowed path (optional but safer)
        # We'll just log a warning for now as libraries can be spread out
        logger.warning(f"Processando symlink: {filepath}")

    # 4. Basic Header validation (Switch specific)
    try:
        with open(filepath, "rb") as f:
            header = f.read(4)
            # NSP/NSZ starts with PFS0
            if path.suffix.lower() in [".nsp", ".nsz"]:
                if header != b"PFS0":
                    raise ValueError(f"Cabeçalho NSP inválido: {header}")
            # XCI/XCZ starts with HEAD at offset 0x100
            elif path.suffix.lower() in [".xci", ".xcz"]:
                f.seek(0x100)
                header_xci = f.read(4)
                if header_xci != b"HEAD":
                    raise ValueError(f"Cabeçalho XCI inválido: {header_xci}")
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Erro ao ler cabeçalho do arquivo: {str(e)}")

    return True


def cleanup_metadata_files(path):
    """Recursively delete macOS metadata files (starting with ._)"""
    logger.info(f"Cleaning up macOS metadata files in {path}...")
    deleted_count = 0
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.startswith("._") or file == ".DS_Store":
                try:
                    os.remove(os.path.join(root, file))
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete metadata file {file}: {e}")
    if deleted_count > 0:
        logger.info(f"Deleted {deleted_count} metadata files.")


def add_library_complete(app, watcher, path):
    """Add a library to settings, database, and watchdog"""
    from settings import add_library_path_to_settings

    with app.app_context():
        # Add to settings
        success, errors = add_library_path_to_settings(path)
        if not success:
            return success, errors

        # Add to database
        add_library(path)

        # Add to watchdog - Handle cases where watcher is None (e.g. from tests or API quirks)
        target_watcher = watcher
        if not target_watcher:
            if hasattr(app, 'watcher') and app.watcher:
                target_watcher = app.watcher
            else:
                import state
                target_watcher = getattr(state, 'watcher', None)

        if target_watcher:
             target_watcher.add_directory(path)
        else:
             logger.warning(f"Could not add {path} to watchdog: No watcher instance found.")

        logger.info(f"Successfully added library: {path}")
        return True, []


def remove_library_complete(app, watcher, path):
    """Remove a library from settings, database, and watchdog with proper cleanup"""
    from settings import delete_library_path_from_settings

    with app.app_context():
        # Remove from watchdog first
        if watcher:
            watcher.remove_directory(path)
        elif hasattr(app, 'watcher') and app.watcher:
            app.watcher.remove_directory(path)

        # Get library object before deletion
        library = Libraries.query.filter_by(path=path).first()
        if library:
            # Get all file IDs from this library before deletion
            file_ids = [f.id for f in library.files]

            # Update Apps table to remove file references and update ownership
            total_apps_updated = 0
            for file_id in file_ids:
                apps_updated = remove_file_from_apps(file_id)
                total_apps_updated += apps_updated

            # Remove titles that no longer have any owned apps
            titles_removed = remove_titles_without_owned_apps()

            # Delete library (cascade will delete files automatically)
            db.session.delete(library)
            db.session.commit()

            if titles_removed > 0:
                logger.info(f"Removed {titles_removed} titles with no owned apps.")

            log_activity("library_removed", details={"path": path})

        # Remove from settings
        success, errors = delete_library_path_from_settings(path)

        invalidate_library_cache()
        return success, errors


def init_libraries(app, watcher, paths):
    with app.app_context():
        # delete non existing libraries (DISABLED - Too dangerous if drive is temporarily disconnected)
        for library in get_libraries():
            path = library.path
            if not os.path.exists(path):
                logger.warning(f"Library {path} is currently inaccessible. It will NOT be deleted from the database to prevent data loss, but it won't be monitored until it reappears.")
                # remove_library_complete(app, watcher, path)

        # add libraries and start watchdog
        logger.info(f"Initializing libraries with paths: {paths}")
        for path in paths:
            if not os.path.exists(path):
                logger.warning(f"Library path {path} does not exist, skipping")
                continue

            # Check if library already exists in database
            existing_library = Libraries.query.filter_by(path=path).first()
            if not existing_library:
                # add library paths to watchdog if necessary
                logger.info(f"Adding new library to watchdog: {path}")
                watcher.add_directory(path)
                add_library(path)
            else:
                # Ensure watchdog is monitoring existing library
                logger.info(f"Adding existing library to watchdog: {path}")
                watcher.add_directory(path)


def add_files_to_library(library, files):
    nb_to_identify = len(files)
    if isinstance(library, int):
        library_id = library
    elif isinstance(library, str) and library.isdigit():
        library_id = int(library)
    else:
        # It's likely a path string
        library_path = library
        library_id = get_library_id(library_path)

    library_path = get_library_path(library_id)
    if not library_path:
        logger.error(f"Could not determine path for library_id={library_id}")
        return

    files_added = 0
    files_updated = 0
    
    logger.info(f"add_files_to_library called with {nb_to_identify} files")

    # Otimização: Agrupar operações e usar flush() ao invés de commit imediato
    for n, filepath in enumerate(files):
        if n % 10 == 0:
            gevent.sleep(0.001)
        if library_path and isinstance(library_path, str):
            file = filepath.replace(library_path, "")
        else:
            file = os.path.basename(filepath)
        logger.debug(f"Processing file ({n + 1}/{nb_to_identify}): {file}")  # Changed to debug to reduce noise

        try:
            # Validate file before adding to DB
            validate_file(filepath)

            file_info = titles_lib.get_file_info(filepath)

            if file_info is None:
                logger.error(f"Failed to get info for file: {file} - file will be skipped.")
                continue

            # Check if file already exists
            existing_file = Files.query.filter_by(filepath=filepath).first()
            if existing_file:
                logger.debug(f"File already exists in DB, updating info/status: {file}")
                # Update size and force re-identification
                existing_file.size = file_info["size"]
                existing_file.identified = False
                files_updated += 1
            else:
                logger.info(f"New file found, adding to DB: {file}")
                new_file = Files(
                    filepath=filepath,
                    library_id=library_id,
                    folder=file_info["filedir"],
                    filename=file_info["filename"],
                    extension=file_info["extension"],
                    size=file_info["size"],
                )
                db.session.add(new_file)
                files_added += 1
            
            # Flush to catch UniqueViolation early in the loop
            db.session.flush()

            log_activity(
                "file_added" if not existing_file else "file_updated",
                title_id=file_info.get("titleId"),
                details={"filename": file_info["filename"], "size": file_info["size"]},
            )
        except Exception as e:
            # Handle specific DB errors like UniqueViolation to keep the scan moving
            if "UniqueViolation" in str(e) or "duplicate key" in str(e).lower():
                logger.warning(f"File {file} already exists (concurrent scan?). Skipping.")
                db.session.rollback()
            else:
                logger.error(f"Error processing file {file}: {str(e)}")
                db.session.rollback()
            continue

        # Otimização: Commit a cada 100 arquivos para reduzir overhead de transações
        # Usar flush() a cada 50 para liberar memória sem commit completo
        if (n + 1) % 50 == 0:
            db.session.flush()  # Libera memória sem commit completo
        if (n + 1) % 100 == 0:
            db.session.commit()  # Commit completo a cada 100 arquivos

    # Commit final
    db.session.commit()
    logger.info(f"add_files_to_library complete: {files_added} files added, {files_updated} files updated")


def scan_library_path(library_path, job_id=None):
    cleanup_metadata_files(library_path)
    library_id = get_library_id(library_path)
    
    # Register and start job if not provided
    if not job_id:
        job_id = job_tracker.register_job('library_scan', {'library_path': library_path})
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
            log_activity("library_scan_error", details={"path": library_path, "error": "Permission denied (no read access)"})
    except:
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
    updated_files = [] # Files where size changed
    for filepath in files:
        if filepath not in filepaths_in_library:
            new_files.append(filepath)
        else:
            # Check if size changed (indicates replacement)
            try:
                disk_size = os.path.getsize(filepath)
                if disk_size != db_files_map[filepath].size:
                    logger.info(f"File size changed for {filepath} ({db_files_map[filepath].size} -> {disk_size}). Marking for re-identification.")
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
                 progress_msg = f"[{lib_name}] Adding new files: {n+1}/{total_new}"
                 job_tracker.update_progress(job_id, 30 + int((n/total_new)*20), message=progress_msg)
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
                progress_msg = f"[{lib_name}] Removing deleted files: {n+1}/{total_del}"
                job_tracker.update_progress(job_id, 60 + int((n/total_del)*20), message=progress_msg)
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
    logger.info(f"Scan complete for {library_path}: {len(new_files)} added, {len(updated_files)} changed, {len(deleted_files)} removed")
    
    job_tracker.update_progress(job_id, 90, message=f"[{lib_name}] Finalizing and updating status...")
    
    if new_files or updated_files or deleted_files:
        logger.info("Triggering post-scan library update to refresh badges and filters")
        post_library_change()
        
    job_tracker.complete_job(job_id, {
        'files_added': len(new_files),
        'files_updated': len(updated_files),
        'files_removed': len(deleted_files),
        'total_files': len(files)
    })
    
    # Log summary
    logger.info(f"Scan complete for {library_path}: {len(new_files)} added, {len(deleted_files)} removed")


def get_files_to_identify(library_id):
    non_identified_files = get_all_non_identified_files_from_library(library_id)

    # Re-identify files identified by "filename" if TitleDB has been updated
    current_titledb_timestamp = titles_lib.get_titledb_cache_timestamp()
    files_to_reidentify = get_filename_identified_files_needing_reidentification(library_id, current_titledb_timestamp)

    if titles_lib.Keys.keys_loaded:
        files_to_identify_with_cnmt = get_files_with_identification_from_library(library_id, "filename")
        non_identified_files = list(
            set(non_identified_files).union(files_to_identify_with_cnmt).union(files_to_reidentify)
        )
    else:
        # Even without keys, re-identify filename files if TitleDB was updated
        non_identified_files = list(set(non_identified_files).union(files_to_reidentify))

    return non_identified_files


def identify_single_file(filepath):
    """
    Identify a single file and create Apps records.
    This is called by the file watcher when new files are detected.
    
    Args:
        filepath: Absolute path to the file to identify
        
    Returns:
        bool: True if identification succeeded, False otherwise
    """
    import titles as titles_lib
    
    # Get file from database
    file_obj = Files.query.filter_by(filepath=filepath).first()
    if not file_obj:
        logger.warning(f"File not found in database: {filepath}")
        return False
    
    # Skip if already identified and has Apps associations
    if file_obj.identified and file_obj.apps and len(file_obj.apps) > 0:
        logger.debug(f"File already identified with Apps: {filepath}")
        return True
    
    # Check if file still exists on disk
    if not os.path.exists(filepath):
        logger.warning(f"File no longer exists on disk: {filepath}")
        try:
             # Remove file from apps associations FIRST
            if file_obj.apps:
                file_obj.apps.clear()
            
            db.session.delete(file_obj)
            db.session.commit()
        except Exception as e:
            logger.error(f"Error removing non-existent file: {e}")
            db.session.rollback()
        return False
    
    try:
        # Ensure TitleDB is loaded
        titles_lib.load_titledb()
        
        # Identify file
        logger.info(f"Identifying single file: {file_obj.filename}")
        identification, success, contents, error = titles_lib.identify_file(filepath)
        
        if not success:
             logger.warning(f"Failed to identify file (skipping): {filepath} - Error: {error}")
             return False

        if success and contents and not error:
            # Clear old associations before adding new ones
            if file_obj.apps:
                file_obj.apps.clear()
            
            # Add title IDs to database
            title_ids = list(dict.fromkeys([c["title_id"] for c in contents]))
            for title_id in title_ids:
                add_title_id_in_db(title_id)
            
            # Create Apps records
            nb_content = 0
            for file_content in contents:
                logger.info(
                    f"Found content - Title ID: {file_content['title_id']} "
                    f"App ID: {file_content['app_id']} "
                    f"Type: {file_content['type']} "
                    f"Version: {file_content['version']}"
                )
                
                title_id_in_db = get_title_id_db_id(file_content["title_id"])
                if not title_id_in_db:
                    # Retry adding it
                    add_title_id_in_db(file_content["title_id"])
                    title_id_in_db = get_title_id_db_id(file_content["title_id"])
                
                if not title_id_in_db:
                     raise Exception(f"Failed to find or create DB record for Title ID {file_content['title_id']}")
                
                # Check if app already exists
                existing_app = get_app_by_id_and_version(
                    file_content["app_id"], 
                    file_content["version"]
                )
                
                if existing_app:
                    # Add file to existing app using many-to-many relationship
                    # Check if connection already exists to avoid duplicates (though set usage helps)
                    if not existing_app.owned:
                        existing_app.owned = True

                    if file_obj not in existing_app.files:
                        existing_app.files.append(file_obj)
                else:
                    # Create new app entry and add file
                    new_app = Apps(
                        app_id=file_content["app_id"],
                        app_version=file_content["version"],
                        app_type=file_content["type"],
                        owned=True,
                        title_id=title_id_in_db,
                    )
                    db.session.add(new_app)
                    db.session.flush()  # Flush to get the app ID
                    
                    # Add the file to the new app
                    new_app.files.append(file_obj)
                
                nb_content += 1
            
            # Update file record
            file_obj.identified = True
            file_obj.identification_type = identification
            file_obj.identification_error = None
            file_obj.nb_content = nb_content
            file_obj.multicontent = nb_content > 1
            file_obj.identification_attempts += 1
            file_obj.last_attempt = now_utc()
            
            # Update TitleDB version timestamp
            current_titledb_ts = titles_lib.get_titledb_cache_timestamp()
            if current_titledb_ts:
                file_obj.titledb_version = str(current_titledb_ts)
            
            db.session.commit()
            logger.info(f"Successfully identified file: {file_obj.filename} ({nb_content} content(s))")
            return True
        else:
            # Identification failed
            file_obj.identified = False
            file_obj.identification_error = error
            file_obj.identification_attempts += 1
            file_obj.last_attempt = now_utc()
            db.session.commit()
            logger.warning(f"Failed to identify file: {file_obj.filename} - {error}")
            return False
            
    except Exception as e:
        logger.error(f"Error identifying file {filepath}: {e}")
        try:
            file_obj.identification_error = str(e)
            file_obj.identified = False
            file_obj.identification_attempts += 1
            file_obj.last_attempt = now_utc()
            db.session.commit()
        except Exception as e:
            logger.debug(f"Failed to save identification error: {e}")
            db.session.rollback()
        return False


def identify_library_files(library):
    if isinstance(library, int):
        library_id = library
        library_path = get_library_path(library_id)
    elif isinstance(library, str) and library.isdigit():
        library_id = int(library)
        library_path = get_library_path(library_id)
    else:
        library_path = library
        library_id = get_library_id(library_path)

    files_to_identify = get_files_to_identify(library_id)
    nb_to_identify = len(files_to_identify)
    logger.info(f"Starting identification for library {library_path}: {nb_to_identify} files to identify")

    # Job tracking
    from job_tracker import job_tracker, JobType
    from socket_helper import get_socketio_emitter
    import time
    import gevent
    from gevent.threadpool import ThreadPool as Pool

    # Ensure TitleDB is loaded for identification
    titles_lib.load_titledb()
    job_tracker.set_emitter(get_socketio_emitter())
    
    job_id = f"identify_{library_id}_{int(time.time())}"
    job_tracker.start_job(job_id, JobType.FILE_IDENTIFICATION, f"Identifying files in {os.path.basename(library_path)}")
    lib_name = os.path.basename(library_path) or library_path
    job_tracker.update_progress(job_id, 0, current=0, total=nb_to_identify, message=f"[{lib_name}] Starting identification...")
    
    if nb_to_identify == 0:
        job_tracker.complete_job(job_id, "No files to identify")
        return

    # Worker function for parallel processing
    def _worker_identify(file_data):
        file_id, filepath, filename = file_data
        try:
            # check existence
            if not os.path.exists(filepath):
                return (file_id, filepath, filename, False, None, "File not found", None)

            # Heavy I/O/CPU operation
            # This runs in OS thread. If it's CPU intensive, it holds GIL.
            identification, success, file_contents, error = titles_lib.identify_file(filepath)
            
            # CRITICAL: Sleep briefly to force GIL release so MainThread (gevent loop) can run
            # Reduced to 10ms to improve speed while maintaining responsiveness
            time.sleep(0.01)
            
            # Gevent yield (for good measure, though running in thread)
            gevent.sleep(0)
            
            return (file_id, filepath, filename, success, file_contents, error, identification)
        except Exception as e:
            logger.error(f"Worker identification error for {filename}: {str(e)}")
            return (file_id, filepath, filename, False, None, str(e), None)

    try:
        # Prepare data for pool
        batch_data = [(f.id, f.filepath, f.filename) for f in files_to_identify]
        
        # Restore concurrency for Postgres (or optimized SQLite)
        pool = Pool(4)
        
        processed_count = 0
        
        # Use imap_unordered to process results as they finish
        for result in pool.imap_unordered(_worker_identify, batch_data):
            
            # Yield to event loop to keep server responsive
            gevent.sleep(0)
            
            # Check cancellation
            if job_tracker.is_cancelled(job_id):
                logger.info(f"Job {job_id} was cancelled by user, stopping identification")
                pool.kill()
                job_tracker.fail_job(job_id, "Cancelled by user")
                return

            # Unpack result
            file_id, filepath, filename, success, file_contents, error, identification_type = result

            processed_count += 1
            
            # Retrieve DB object freshly for this session/thread
            try:
                file_obj = get_file_from_db(file_id)
                if not file_obj:
                    continue

                if error == "File not found":
                    logger.warning(f"File {filename} no longer exists during identification cleanup.")
                    remove_file_from_apps(file_id)
                    Files.query.filter_by(id=file_id).delete(synchronize_session=False)
                
                elif success and file_contents:
                    # Clear old associations
                    remove_file_from_apps(file_id)

                    # Increment metrics
                    try:
                        FILES_IDENTIFIED.labels(
                            app_type="multiple" if len(file_contents) > 1 else file_contents[0]["type"]
                        ).inc()
                    except:
                        pass
                    
                    # Add title IDs to DB
                    title_ids = list(dict.fromkeys([c["title_id"] for c in file_contents]))
                    for title_id in title_ids:
                        add_title_id_in_db(title_id)

                    nb_content = 0
                    for file_content in file_contents:
                        title_id_in_db = get_title_id_db_id(file_content["title_id"])
                        
                        # Check/Create App
                        update_or_create_app_and_link_file(
                            file_content["app_id"],
                            file_content["version"],
                            file_content["type"],
                            title_id_in_db,
                            file_obj
                        )
                        nb_content += 1

                    if nb_content > 1:
                        file_obj.multicontent = True
                    file_obj.nb_content = nb_content
                    file_obj.identified = True
                    file_obj.identification_error = None
                    
                    logger.info(f"Identified {filename} ({nb_content} content)")
                else:
                    # Failure case
                    logger.warning(f"Error identifying file {filename}: {error}")
                    file_obj.identification_error = error
                    file_obj.identified = False

                if identification_type:
                    file_obj.identification_type = identification_type

                file_obj.identification_attempts += 1
                file_obj.last_attempt = now_utc()
                
                current_titledb_ts = titles_lib.get_titledb_cache_timestamp()
                if current_titledb_ts:
                    file_obj.titledb_version = str(current_titledb_ts)

                # Flush instead of commit for performance, commit in batches
                db.session.flush()

                # Optimization: Commit every 50 files or on completion
                if processed_count % 50 == 0:
                    db.session.commit()
                    logger.debug(f"Batch commit at {processed_count} files")
            
            except Exception as e:
                logger.error(f"Error processing identification result for {filename}: {e}")
                db.session.rollback()
                # Toast notification attempting
                try:
                    from app import socketio
                    socketio.emit("notification", {"title": "Error", "message": f"Falha ao salvar {filename}: {str(e)}", "type": "error"}, namespace="/")
                except:
                    pass

            # More frequent yields to keep system responsive
            if processed_count % 10 == 0:
                gevent.sleep(0)
            
            # Prepare formatted name for UI
            display_name = filename
            if success and file_contents:
                try:
                    tid = file_contents[0].get("title_id")
                    if tid:
                        info = titles_lib.get_game_info(tid)
                        if info and info.get("name"):
                            display_name = info.get("name")
                except Exception:
                    pass  # Use filename if game info unavailable

            # Frequent progress updates (UI feels faster)
            # Throttle updates for large sets to prevent UI freeze
            should_update_ui = True
            if nb_to_identify > 500 and processed_count % 5 != 0:
                 should_update_ui = False
            if nb_to_identify > 2000 and processed_count % 20 != 0:
                 should_update_ui = False
                 
            if should_update_ui or processed_count == nb_to_identify:
                progress = int((processed_count / nb_to_identify) * 100)
                lib_name = os.path.basename(library_path) or library_path
                if display_name != filename:
                    msg = f"[{lib_name}] {processed_count}/{nb_to_identify}: {display_name} ({filename})"
                else:
                    msg = f"[{lib_name}] {processed_count}/{nb_to_identify}: {filename}"
                    
                job_tracker.update_progress(job_id, progress, current=processed_count, total=nb_to_identify, message=msg)
                gevent.sleep(0)  # Yield after progress update

        # Final commit (just in case)
        try:
            db.session.commit()
        except:
             db.session.rollback()
        pool.join()

        job_tracker.complete_job(job_id, f"Identified {processed_count} files")
    
    except Exception as e:
        logger.exception(f"Error identifying files: {e}")
        job_tracker.fail_job(job_id, str(e))
    finally:
        if 'pool' in locals():
            pool.kill()

def update_or_create_app_and_link_file(app_id, version, app_type, title_id_db, file_obj):
    # Retry loop for deadlocks
    for attempt in range(5):
        try:
            with db.session.no_autoflush:
                existing_app = get_app_by_id_and_version(app_id, version)
                if existing_app:
                    if not existing_app.owned:
                        existing_app.owned = True
            
                    if file_obj not in existing_app.files:
                        existing_app.files.append(file_obj)
                else:
                    new_app = Apps(
                        app_id=app_id,
                        app_version=version,
                        app_type=app_type,
                        owned=True,
                        title_id=title_id_db,
                    )
                    db.session.add(new_app)
                    try:
                        db.session.flush()
                    except Exception:
                        # If flush fails due to race condition (another thread created it), check again
                        db.session.rollback()
                        existing_app = get_app_by_id_and_version(app_id, version)
                        if existing_app:
                            if file_obj not in existing_app.files:
                                existing_app.files.append(file_obj)
                        else:
                            raise # Re-raise if it wasn't a race condition
                            
                    if new_app in db.session:
                        new_app.files.append(file_obj)
                
                # Small yield to reduce contention
                gevent.sleep(0.01)
                break # Success
                
        except Exception as e:
            if "deadlock" in str(e).lower() and attempt < 4:
                db.session.rollback()
                logger.warning(f"Deadlock detected creating app {app_id}, retrying ({attempt+1}/5)...")
                time.sleep(0.1 * (attempt + 1))
                continue
            else:
                raise e


def add_missing_apps_to_db():
    logger.info("Adding missing apps to database...")
    titles = get_all_titles()
    apps_added = 0

    for n, title in enumerate(titles):
        # Yield to other gevent co-routines
        import gevent
        gevent.sleep(0)

        title_id = title.title_id
        title_db_id = get_title_id_db_id(title_id)

        # Add base game if not present
        existing_base = get_app_by_id_and_version(title_id, "0")

        if not existing_base:
            new_base_app = Apps(
                app_id=title_id, app_version="0", app_type=APP_TYPE_BASE, owned=False, title_id=title_db_id
            )
            db.session.add(new_base_app)
            apps_added += 1
            logger.debug(f"Added missing base app: {title_id}")

        # Add missing update versions
        title_versions = titles_lib.get_all_existing_versions(title_id)
        for version_info in title_versions:
            v_int = version_info["version"]
            if v_int == 0:
                continue  # Skip v0 for updates table

            version = str(v_int)
            update_app_id = title_id[:-3] + "800"  # Convert base ID to update ID

            existing_update = get_app_by_id_and_version(update_app_id, version)

            if not existing_update:
                new_update_app = Apps(
                    app_id=update_app_id, app_version=version, app_type=APP_TYPE_UPD, owned=False, title_id=title_db_id
                )
                db.session.add(new_update_app)
                apps_added += 1
                logger.debug(f"Added missing update app: {update_app_id} v{version}")

        # Add missing DLC
        title_dlc_ids = titles_lib.get_all_existing_dlc(title_id)
        for dlc_app_id in title_dlc_ids:
            dlc_versions = titles_lib.get_all_app_existing_versions(dlc_app_id)
            if dlc_versions:
                for dlc_version in dlc_versions:
                    existing_dlc = get_app_by_id_and_version(dlc_app_id, str(dlc_version))

                    if not existing_dlc:
                        new_dlc_app = Apps(
                            app_id=dlc_app_id,
                            app_version=str(dlc_version),
                            app_type=APP_TYPE_DLC,
                            owned=False,
                            title_id=title_db_id,
                        )
                        db.session.add(new_dlc_app)
                        apps_added += 1
                        logger.debug(f"Added missing DLC app: {dlc_app_id} v{dlc_version}")

        # Commit every 100 titles to avoid excessive memory use
        if (n + 1) % 100 == 0:
            db.session.commit()
            logger.info(f"Processed {n + 1}/{len(titles)} titles, added {apps_added} missing apps so far")

    # Final commit
    db.session.commit()
    logger.info(f"Finished adding missing apps to database. Total apps added: {apps_added}")


def trigger_library_update_notification():
    """Helper function to trigger library update notifications (used by Celery tasks)"""
    try:
        from app import socketio
        import datetime

        socketio.emit("library_updated", {"timestamp": now_utc().isoformat()}, namespace="/")
    except Exception as e:
        logger.debug(f"Could not emit library_updated event: {e}")


def process_library_identification(app):
    logger.info("Starting library identification process for all libraries...")
    try:
        with app.app_context():
            libraries = get_libraries()
            for library in libraries:
                identify_library_files(library.path)

    except Exception as e:
        logger.error(f"Error during library identification process: {e}")
    logger.info("Library identification process for all libraries completed.")


def update_titles():
    # Remove titles that no longer have any owned apps
    titles_removed = remove_titles_without_owned_apps()
    if titles_removed > 0:
        logger.info(f"Removed {titles_removed} titles with no owned apps.")

    # Auto-heal: Ensure apps with files are marked as owned
    # This fixes cases where files were linked but 'owned' flag wasn't updated due to bugs
    try:
        # FIX: PostgreSQL requires boolean comparison (owned = true), not integer (owned = 1)
        db.session.execute(db.text("UPDATE apps SET owned = true WHERE id IN (SELECT app_id FROM app_files) AND owned = false"))
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
        max_available_version = max([v["version"] for v in available_versions], default=0)

        # check up_to_date - consider current max owned vs max available
        up_to_date = max_owned_version >= max_available_version

        # check complete - check against TitleDB known DLCs
        all_possible_dlc_ids = [d.upper() for d in titles_lib.get_all_existing_dlc(title_id)]
        all_possible_dlc_ids = [d for d in all_possible_dlc_ids if d != title_id.upper()]
        
        if not all_possible_dlc_ids:
            complete = True
        else:
            owned_dlc_ids = set([a.app_id.upper() for a in title.apps 
                                 if a.app_type == APP_TYPE_DLC and a.owned and len(a.files) > 0])
            complete = all(d in owned_dlc_ids for d in all_possible_dlc_ids)

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
    
    # FIX for Issue #4: Remove orphaned titles at the END of update_titles
    # and invalidate cache if any were removed.
    titles_removed = remove_titles_without_owned_apps()
    if titles_removed > 0:
        logger.info(f"Cleaned up {titles_removed} orphaned titles with no remaining files.")
        # We don't call post_library_change here to avoid infinite recursion if 
        # post_library_change calls update_titles, but we do need to invalidate cache.
        global _LIBRARY_CACHE
        with _CACHE_LOCK:
            _LIBRARY_CACHE = None
        invalidate_library_cache()


def get_library_status(title_id):
    title = get_title(title_id)
    title_apps = get_all_title_apps(title_id)

    available_versions = titles_lib.get_all_existing_versions(title_id)
    for version in available_versions:
        if len(
            list(
                filter(
                    lambda x: x.get("app_type") == APP_TYPE_UPD
                    and str(x.get("app_version")) == str(version["version"]),
                    title_apps,
                )
            )
        ):
            version["owned"] = True
        else:
            version["owned"] = False

    library_status = {
        "has_base": title.have_base,
        "has_latest_version": title.up_to_date,
        "version": available_versions,
        "has_all_dlcs": title.complete,
    }
    return library_status


def compute_apps_hash():
    """
    Computes a hash of all Apps table content and custom metadata to detect changes.
    """
    hash_md5 = hashlib.md5()
    apps = get_all_apps()

    # Sort apps with safe handling of None values
    for app in sorted(apps, key=lambda x: (x["app_id"] or "", str(x.get("app_version") or ""))):
        hash_md5.update((app["app_id"] or "").encode())
        hash_md5.update(str(app.get("app_version") or "").encode())
        hash_md5.update((app["app_type"] or "").encode())
        hash_md5.update(str(app["owned"] or False).encode())
        hash_md5.update((app["title_id"] or "").encode())
        if "files_info" in app:
            for f in sorted(app["files_info"], key=lambda x: x["path"]):
                hash_md5.update(f["path"].encode())
                hash_md5.update(str(f.get("size", 0)).encode())

    # Include tags in hash
    titles_with_tags = db.session.query(Titles.title_id, Tag.name).join(Titles.tags).all()
    for tid, tname in sorted(titles_with_tags):
        hash_md5.update(tid.encode())
        hash_md5.update(tname.encode())

    # CRITICAL: Include custom.json modification time in hash
    custom_path = os.path.join(TITLEDB_DIR, "custom.json")
    if os.path.exists(custom_path):
        mtime = os.path.getmtime(custom_path)
        hash_md5.update(str(mtime).encode())

    return hash_md5.hexdigest()


def is_library_unchanged():
    cache_path = Path(LIBRARY_CACHE_FILE)
    if not cache_path.exists():
        return False

    saved_library = load_library_from_disk()
    if not saved_library:
        return False

    if not saved_library.get("hash"):
        return False

    current_hash = compute_apps_hash()
    return saved_library["hash"] == current_hash


def save_library_to_disk(library_data):
    cache_path = Path(LIBRARY_CACHE_FILE)
    # Ensure cache directory exists
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_json(cache_path, library_data)


def load_library_from_disk():
    cache_path = Path(LIBRARY_CACHE_FILE)
    if not cache_path.exists():
        return None

    try:
        with cache_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        logger.debug(f"Failed to load library cache: {e}")
        return None


def invalidate_library_cache():
    global _LIBRARY_CACHE
    with _CACHE_LOCK:
        _LIBRARY_CACHE = None
        # Also remove disk cache so it's forced to re-generate
        cache_path = Path(LIBRARY_CACHE_FILE)
        if cache_path.exists():
            try:
                cache_path.unlink()
                logger.info("Library disk cache invalidated (deleted).")
            except Exception as e:
                logger.error(f"Failed to delete library cache file: {e}")


def get_game_info_item(tid, title_data):
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
        # Fallback: find a filename from associated files if possible
        display_name = f"Unknown ({tid})"
        if all_title_apps:
            # Try to find a file from any app associated with this title
            for app_meta in all_title_apps:
                if app_meta.get('files') and len(app_meta['files']) > 0:
                    display_name = os.path.basename(app_meta['files'][0]['filepath'])
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

    # Determine if ALL possible DLCs are owned
    all_possible_dlc_ids = [d.upper() for d in titles_lib.get_all_existing_dlc(tid)]
    # We only count as owned if there's actually a file attached
    owned_dlc_ids = list(set([a["app_id"].upper() for a in all_title_apps 
                              if a["app_type"] == APP_TYPE_DLC and a["owned"] and len(a.get("files_info", [])) > 0]))
    
    # Filter out self-mapping if it somehow appeared
    all_possible_dlc_ids = [d for d in all_possible_dlc_ids if d != tid.upper()]
    
    game["has_all_dlcs"] = all(d in owned_dlc_ids for d in all_possible_dlc_ids) if all_possible_dlc_ids else True

    # Check for redundant updates (more than 1 update file)
    owned_updates = [a for a in all_title_apps if a["app_type"] == APP_TYPE_UPD and a["owned"]]
    game["updates_count"] = len(owned_updates)
    game["has_redundant_updates"] = game["updates_count"] > 1

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

    # Screenshots from TitleDB
    info = titles_lib.get_game_info(tid)
    game["screenshots"] = info.get("screenshots", []) if info else []

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
    from db import TitleMetadata
    remote_meta = TitleMetadata.query.filter_by(title_id=tid).all()
    for meta in remote_meta:
        if meta.rating and not game.get("metacritic_score"):
            game["metacritic_score"] = int(meta.rating)
        if meta.description and (not game.get("description") or len(meta.description) > len(game.get("description", ""))):
            game["description"] = meta.description
        if meta.rating and not game.get("rawg_rating"):
            game["rawg_rating"] = meta.rating / 20.0
        
        # API Genres and Tags
        if meta.genres:
            existing_cats = set(game.get("category", []) if isinstance(game.get("category"), list) else [])
            for g in meta.genres:
                if g not in existing_cats:
                    game.setdefault("category", []).append(g)

        if meta.tags:
            existing_tags = set(game.get("tags", []) if isinstance(game.get("tags"), list) else [])
            for t in meta.tags:
                if t not in existing_tags:
                    game.setdefault("tags", []).append(t)

    # API Genres and Tags from Title Object (fallback/merged)
    api_genres = title_data.get("genres_json") or []
    if api_genres:
        existing_cats = set(game.get("category", []) if isinstance(game.get("category"), list) else [])
        for g in api_genres:
            if g not in existing_cats:
                game.setdefault("category", []).append(g)

    api_tags = title_data.get("tags_json") or []
    if api_tags:
        existing_tags = set(game.get("tags", []) if isinstance(game.get("tags"), list) else [])
        for t in api_tags:
            if t not in existing_tags:
                game.setdefault("tags", []).append(t)

    # API Screenshots
    api_screenshots = title_data.get("screenshots_json") or []
    if api_screenshots:
        # Normalize existing screenshots to URLs for comparison
        existing_urls = set()
        for s in game.get("screenshots", []):
            if isinstance(s, dict):
                existing_urls.add(s.get("url"))
            elif isinstance(s, str):
                existing_urls.add(s)

        for s in api_screenshots:
            s_url = s.get("url") if isinstance(s, dict) else s
            if s_url and s_url not in existing_urls:
                game.setdefault("screenshots", []).append(s)

    update_apps = [a for a in all_title_apps if a["app_type"] == APP_TYPE_UPD]
    update_apps_by_version = {int(a["app_version"] or 0): a for a in update_apps}
    
    version_list = []
    # Include all versions found in versions.json
    for v_info in available_versions:
        v_int = v_info["version"]
        if v_int == 0: continue
        
        upd_app = update_apps_by_version.get(v_int)
        version_list.append({
            "version": v_int,
            "owned": upd_app["owned"] if upd_app else False,
            "release_date": v_info["release_date"] or "Unknown",
            "files": upd_app.get("files", []) if upd_app and upd_app["owned"] else []
        })
    
    # Also include any owned updates that might NOT be in versions.json (rare but possible)
    for v_int, upd_app in update_apps_by_version.items():
        if v_int not in [v["version"] for v in version_list] and v_int != 0:
            version_list.append({
                "version": v_int,
                "owned": upd_app["owned"],
                "release_date": "Unknown",
                "files": upd_app.get("files", []) if upd_app["owned"] else []
            })

    game["updates"] = sorted(version_list, key=lambda x: x["version"], reverse=True)

    # DLC details for the JSON response
    dlcs_by_id = {}
    for dlc_id in all_possible_dlc_ids:
        # Filter out self-mapping
        if dlc_id == tid.upper():
            continue
            
        dlcs_by_id[dlc_id] = {
            "app_id": dlc_id,
            "name": titles_lib.get_game_info(dlc_id).get("name", f"DLC {dlc_id}"),
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
                "name": titles_lib.get_game_info(aid).get("name", f"DLC {aid}"),
                "owned": False,
                "latest_version": 0,
                "owned_version": 0,
            }
        
        # Mark as owned only if it has files
        if dlc_app["owned"] and len(dlc_app.get("files_info", [])) > 0:
            dlcs_by_id[aid]["owned"] = True
            dlcs_by_id[aid]["owned_version"] = max(dlcs_by_id[aid]["owned_version"], v)
        dlcs_by_id[aid]["latest_version"] = max(dlcs_by_id[aid]["latest_version"], v)

    game["dlcs"] = sorted(dlcs_by_id.values(), key=lambda x: x["name"])
    return game


def generate_library(force=False):
    """Generate the game library grouped by TitleID, using cached version if unchanged"""
    global _LIBRARY_CACHE

    if not force:
        with _CACHE_LOCK:
            # Check if memory cache exists AND is still valid for the current DB state
            if _LIBRARY_CACHE and is_library_unchanged():
                return _LIBRARY_CACHE

            # If not in memory or DB changed, try loading from disk and VALIDATE hash
            if is_library_unchanged():
                saved_library = load_library_from_disk()
                if saved_library and "library" in saved_library:
                    _LIBRARY_CACHE = saved_library["library"]
                    logger.info("Library loaded from disk cache.")
                    return _LIBRARY_CACHE
            else:
                logger.info("Library state changed or disks/DB out of sync, rebuilding cache.")

    logger.info(f"Generating library (force={force})...")
    logger.info("generate_library: Loading TitleDB...")
    titles_lib.load_titledb()
    logger.info("generate_library: TitleDB loaded.")

    # Get all Titles known to the system with their apps and files pre-loaded
    logger.info("generate_library: Fetching titles from DB...")
    all_titles_data = get_all_titles_with_apps()
    logger.info(f"generate_library: Fetched {len(all_titles_data)} titles. Processing...")
    games_info = []

    import gevent
    processed_count = 0
    for idx, title_data in enumerate(all_titles_data):
        game = get_game_info_item(title_data["title_id"], title_data)
        if game:
            games_info.append(game)
            processed_count += 1
        
        # Yield every 50 games to keep server responsive
        if idx % 50 == 0:
            logger.info(f"generate_library: Processed {idx}/{len(all_titles_data)} titles. Found {len(games_info)} games so far.")
            gevent.sleep(0)
    
    logger.info(f"generate_library: Finished processing Titles. Total games found: {len(games_info)}")

    sorted_library = sorted(games_info, key=lambda x: x.get("name", "Unrecognized") or "Unrecognized")

    library_data = {"hash": compute_apps_hash(), "library": sorted_library}

    save_library_to_disk(library_data)

    with _CACHE_LOCK:
        _LIBRARY_CACHE = sorted_library

    titles_lib.identification_in_progress_count -= 1
    titles_lib.unload_titledb()

    # Update library size metric
    total_size = sum(g.get("size", 0) for g in games_info)
    LIBRARY_SIZE.set(total_size)

    logger.info(f"Generating library done. Found {len(games_info)} games used for response.")
    
    # Emit notification with game count
    try:
        from app import socketio
        socketio.emit("notification", {"title": "Library Updated", "message": f"Biblioteca atualizada: {len(games_info)} jogos encontrados.", "type": "info"}, namespace="/")
    except:
        pass
    
    if len(games_info) == 0:
        # Diagnostic: Why is it empty?
        count_files = Files.query.count()
        count_titles = Titles.query.count()
        count_apps = Apps.query.count()
        logger.warning(f"Library is empty! DB Stats: Files={count_files}, Titles={count_titles}, Apps={count_apps}")
        
    return sorted_library


def post_library_change():
    """Called after library changes to update titles and regenerate library cache"""
    import gevent
    
    def _do_post_library_change():
        from app import app
        
        with app.app_context():
            global _LIBRARY_CACHE
            
            logger.info("Post-library change: updating titles and cache")
            
            try:
                # 1. Invalidate in-memory cache FIRST
                with _CACHE_LOCK:
                    _LIBRARY_CACHE = None
                
                # 2. Delete disk cache
                invalidate_library_cache()
                
                # 3. Update titles with new files
                # This is critical for updating 'up_to_date' and 'complete' status flags
                # which control the badges (UPDATE, DLC) and filters
                update_titles()
                
                # 4. Regenerate library cache (force=True) to ensure fresh data
                # This is expensive so we yield periodically
                gevent.sleep(0)
                generate_library(force=True)
                
                # 5. Notify frontend via WebSocket
                trigger_library_update_notification()
                
                logger.info("Library cache regenerated successfully")
            except Exception as e:
                logger.error(f"Error in post_library_change: {e}")
                import traceback
                traceback.print_exc()

            titles_lib.unload_titledb()
    
    # Run in background so it doesn't block the scan job completion
    gevent.spawn(_do_post_library_change)


def reidentify_all_files_job():
    """Re-identify all files from scratch"""
    from job_tracker import job_tracker
    import gevent
    import datetime
    from app import app
    from db import db, Files, Apps
    
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
            stmt = Files.query.update({
                'identified': False,
                'identification_error': None,
                'identification_attempts': 0
            })
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
                
                job_tracker.update_progress(
                    job_id, 
                    progress, 
                    100,
                    f"Identifying {file_obj.filename} ({i+1}/{total})"
                )
                
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
        base_id = title_id.upper().rstrip('0')
        update_id = base_id + '800'
        
        # Convert version number to string (e.g., 131072 -> "2.0.0")
        version_string = version_to_string(latest.get("version", 0))
        
        return {
            "version": latest.get("version", 0),
            "version_string": version_string,
            "update_id": update_id,
            "release_date": latest.get("releaseDate") or latest.get("release_date") or "Unknown"
        }
    except Exception as e:
        logger.error(f"Error getting pending update info for {title_id}: {e}")
        return None

