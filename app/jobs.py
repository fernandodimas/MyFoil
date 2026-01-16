"""
MyFoil - Background Jobs Module
Contains scheduled job functions for library scanning, TitleDB updates, and backups
"""
import logging
import threading
import datetime
from datetime import timedelta

logger = logging.getLogger('jobs')


def update_titledb_job(app=None, force=False):
    """Update TitleDB in background
    
    Args:
        app: Flask app instance for app context
        force: Force update even if no changes detected
    
    Returns:
        bool: True if update was performed, False otherwise
    """
    from app import is_titledb_update_running, titledb_update_lock, load_settings, log_activity
    from app import add_missing_apps_to_db, update_titles, generate_library
    
    with titledb_update_lock:
        if is_titledb_update_running:
            logger.info("TitleDB update already in progress.")
            return False
        is_titledb_update_running = True

    logger.info("Starting TitleDB update job...")
    try:
        current_settings = load_settings()
        import titledb
        titledb.update_titledb(current_settings, force=force)

        if app:
            with app.app_context():
                logger.info("Syncing new TitleDB versions to library...")
                add_missing_apps_to_db()
                update_titles()
                generate_library(force=True)
                logger.info("Library cache regenerated after TitleDB update.")
        else:
            logger.warning("No app context available for post-update sync")

        logger.info("TitleDB update job completed.")
        return True
    except Exception as e:
        logger.error(f"Error during TitleDB update job: {e}")
        try:
            log_activity('titledb_update_failed', details={'error': str(e)})
        except:
            pass
        return False
    finally:
        with titledb_update_lock:
            is_titledb_update_running = False


def scan_library_job(app=None):
    """Scan library in background
    
    Args:
        app: Flask app instance for app context
    
    Returns:
        None
    """
    from app import is_titledb_update_running, titledb_update_lock, scan_in_progress, scan_lock
    from app import scan_library, post_library_change, log_activity
    from metrics import ACTIVE_SCANS
    from settings import CELERY_ENABLED
    
    with titledb_update_lock:
        if is_titledb_update_running:
            logger.info("Skipping scheduled library scan: update_titledb job is currently in progress.")
            if app and hasattr(app, 'scheduler'):
                app.scheduler.add_job(
                    job_id=f'scan_library_rescheduled_{datetime.datetime.now().timestamp()}',
                    func=lambda: scan_library_job(app),
                    run_once=True,
                    start_date=datetime.datetime.now().replace(microsecond=0) + timedelta(minutes=5)
                )
            return

    logger.info("Starting library scan job...")
    with scan_lock:
        if scan_in_progress:
            logger.info('Skipping library scan: scan already in progress.')
            return
        scan_in_progress = True
    
    try:
        with ACTIVE_SCANS.track_inprogress():
            if CELERY_ENABLED:
                from tasks import scan_all_libraries_async
                scan_all_libraries_async.delay()
                logger.info("Scheduled library scan queued to Celery.")
            else:
                scan_library()
                if app:
                    with app.app_context():
                        post_library_change()
                else:
                    post_library_change()
        
        if app:
            with app.app_context():
                log_activity('library_scan_completed')
        else:
            log_activity('library_scan_completed')
        
        logger.info("Library scan job completed.")
    except Exception as e:
        logger.error(f"Error during library scan job: {e}")
        try:
            if app:
                with app.app_context():
                    log_activity('library_scan_failed', details={'error': str(e)})
            else:
                log_activity('library_scan_failed', details={'error': str(e)})
        except:
            pass
    finally:
        with scan_lock:
            scan_in_progress = False


def create_backup_job(app=None):
    """Create automatic backup
    
    Args:
        app: Flask app instance for app context
    
    Returns:
        tuple: (success: bool, timestamp: str or None)
    """
    from app import backup_manager
    
    if not backup_manager:
        logger.warning("Backup manager not initialized")
        return False, None
    
    logger.info("Starting automatic backup...")
    try:
        success, timestamp = backup_manager.create_backup()
        if success:
            logger.info(f"Automatic backup completed: {timestamp}")
            return True, timestamp
        else:
            logger.error("Automatic backup failed")
            return False, None
    except Exception as e:
        logger.error(f"Error during backup job: {e}")
        return False, None


def combined_update_and_scan_job(app=None):
    """Combined TitleDB update and library scan job
    
    Args:
        app: Flask app instance for app context
    
    Returns:
        None
    """
    logger.info("Starting combined TitleDB update and library scan...")
    
    # Update TitleDB first
    update_result = update_titledb_job(app=app)
    
    # Then scan library
    scan_library_job(app=app)
    
    logger.info("Combined job completed.")


def schedule_jobs(app, run_now=False):
    """Schedule all background jobs
    
    Args:
        app: Flask app instance
        run_now: Whether to run jobs immediately
    
    Returns:
        None
    """
    if not hasattr(app, 'scheduler'):
        logger.warning("Scheduler not available")
        return
    
    # TitleDB checks 3 times daily (6:00, 14:00, 22:00)
    app.scheduler.add_job(
        job_id='titledb_check_1',
        func=lambda: update_titledb_job(app),
        cron="0 6 * * *",
        run_first=run_now
    )
    app.scheduler.add_job(
        job_id='titledb_check_2',
        func=lambda: update_titledb_job(app),
        cron="0 14 * * *",
        run_first=False
    )
    app.scheduler.add_job(
        job_id='titledb_check_3',
        func=lambda: update_titledb_job(app),
        cron="0 22 * * *",
        run_first=False
    )
    
    # Library scan every 6 hours
    app.scheduler.add_job(
        job_id='library_scan',
        func=lambda: scan_library_job(app),
        interval=timedelta(hours=6),
        run_first=False
    )
    
    # Daily backup at 3:00 AM
    app.scheduler.add_job(
        job_id='daily_backup',
        func=lambda: create_backup_job(app),
        interval=timedelta(days=1),
        run_first=False,
        start_date=datetime.datetime.now().replace(hour=3, minute=0, second=0, microsecond=0)
    )
    
    logger.info("Background jobs scheduled")
