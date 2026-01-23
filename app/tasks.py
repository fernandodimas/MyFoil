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


@celery.task(name="tasks.fetch_metadata_for_game_async")
def fetch_metadata_for_game_async(title_id):
    """Fetch metadata for a single game"""
    with flask_app.app_context():
        from db import Titles
        from services.rating_service import update_game_metadata

        game = Titles.query.filter_by(title_id=title_id).first()
        if not game:
            logger.error("game_not_found", title_id=title_id)
            return False

        logger.info("fetching_metadata", title_id=title_id, name=game.name)
        return update_game_metadata(game, force=False)


@celery.task(name="tasks.fetch_metadata_for_all_games_async")
def fetch_metadata_for_all_games_async():
    """Background task to fetch metadata for ALL games"""
    with flask_app.app_context():
        from db import Titles
        from services.rating_service import update_game_metadata
        from job_tracker import job_tracker, JobType, JobStatus
        from app import socketio
        import time

        job_id = f"metadata_{int(time.time())}"
        job_tracker.start_job(job_id, JobType.METADATA_FETCH, "Fetching metadata for all games")
        socketio.emit('job_update', job_tracker.get_status())
        
        try:
            # Only fetch for games that have at least the base game (identified)
            games = Titles.query.filter(Titles.have_base == True).all()
            total = len(games)
            logger.info("metadata_batch_started", count=total)

            if total == 0:
                job_tracker.complete_job(job_id, "No games to update")
                socketio.emit('job_update', job_tracker.get_status())
                return True
            
            job_tracker.update_progress(job_id, 0, current=0, total=total)
            
            for i, game in enumerate(games):
                # We run synchronously here to track progress of the batch
                try:
                    update_game_metadata(game, force=False)
                except Exception as ex:
                    logger.error(f"Error updating {game.name}: {ex}")

                progress = int(((i + 1) / total) * 100)
                job_tracker.update_progress(job_id, progress, current=i+1, total=total, message=f"Updated {game.name}")
                
                if i % 5 == 0:
                    socketio.emit('job_update', job_tracker.get_status())

            job_tracker.complete_job(job_id, f"Finished updating {total} games")
            socketio.emit('job_update', job_tracker.get_status())
            return True
            
        except Exception as e:
            job_tracker.fail_job(job_id, str(e))
            socketio.emit('job_update', job_tracker.get_status())
            logger.error(f"Error in metadata batch: {e}")
            return False
