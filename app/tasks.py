from celery_app import celery
from flask import Flask
from db import db
from library import scan_library_path, identify_library_files, update_titles, generate_library
import structlog

logger = structlog.get_logger("main")


def create_app_context():
    """Create a minimal app context for celery tasks"""
    app = Flask(__name__)
    # We need to reach constants for DB path
    from constants import MYFOIL_DB

    app.config["SQLALCHEMY_DATABASE_URI"] = MYFOIL_DB
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


flask_app = create_app_context()


@celery.task(name="tasks.scan_library_async")
def scan_library_async(library_path):
    """Full library scan in background"""
    with flask_app.app_context():
        from db import remove_missing_files_from_db

        logger.info("background_scan_started", library_path=library_path)

        # 1. Cleanup missing files first
        remove_missing_files_from_db()

        # 2. Scan for new files
        scan_library_path(library_path)

        # 3. Identify new/unidentified files
        identify_library_files(library_path)

        # 4. Update title statuses and regenerate cache
        update_titles()
        generate_library(force=True)

        # Notificar via socketio
        from library import trigger_library_update_notification

        trigger_library_update_notification()

        logger.info("background_scan_completed", library_path=library_path)
        return True


@celery.task(name="tasks.identify_file_async")
def identify_file_async(filepath):
    """Identify a single file in background (e.g. from watchdog)"""
    with flask_app.app_context():
        from db import remove_missing_files_from_db

        logger.info("background_identification_started", triggered_by=filepath)

        # For simple file changes, we can just run the global cleanup and identification
        remove_missing_files_from_db()

        from library import Libraries

        libraries = Libraries.query.all()
        for lib in libraries:
            identify_library_files(lib.path)

        # Atualizar títulos e gerar biblioteca (equivalente a post_library_change)
        update_titles()
        generate_library(force=True)

        # Notificar via socketio
        from library import trigger_library_update_notification

        trigger_library_update_notification()

        return True


@celery.task(name="tasks.scan_all_libraries_async")
def scan_all_libraries_async():
    """Full library scan for all configured paths in background"""
    with flask_app.app_context():
        from db import remove_missing_files_from_db, get_libraries

        logger.info("Background task: Starting full library scan for all paths")

        remove_missing_files_from_db()

        libraries = get_libraries()
        for lib in libraries:
            logger.info("scanning_path", path=lib.path)
            scan_library_path(lib.path)
            identify_library_files(lib.path)

        # Atualizar títulos e gerar biblioteca
        update_titles()
        generate_library(force=True)

        # Notificar via socketio
        from library import trigger_library_update_notification

        trigger_library_update_notification()

        logger.info("Background task: Full scan completed.")
        return True
