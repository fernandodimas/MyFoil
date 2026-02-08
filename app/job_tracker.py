from __future__ import annotations
from dataclasses import dataclass, field
import datetime
from datetime import timedelta
from typing import Optional, Dict, Any, List
import uuid
import logging
from utils import now_utc

logger = logging.getLogger(__name__)


class JobType:
    LIBRARY_SCAN = "library_scan"
    TITLEDB_UPDATE = "titledb_update"
    METADATA_FETCH = "metadata_fetch"
    FILE_IDENTIFICATION = "file_identification"
    BACKUP = "backup"
    CLEANUP = "cleanup"
    OTHER = "other"


class JobStatus:
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobState:
    """Internal state of a job"""

    job_id: str
    job_type: str
    status: str
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None
    progress: Dict[str, Any] = field(default_factory=lambda: {"percent": 0, "message": ""})
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class JobTracker:
    """Singleton to track system jobs with database persistence for cross-process support"""

    def __init__(self):
        self.emitter = None
        self.app = None
        self.cancelled_jobs = set()
        self._last_update_time = {}  # job_id -> timestamp
        self._last_progress = {}  # job_id -> last_percent

    def init_app(self, app):
        """Initialize with Flask app instance"""
        self.app = app
        logger.debug("JobTracker initialized with app")

    def set_emitter(self, emitter):
        """Set the SocketIO emitter for real-time updates"""
        self.emitter = emitter
        logger.debug("JobTracker emitter set")

    def cleanup_stale_jobs(self):
        """Reset jobs stuck in RUNNING or SCHEDULED to FAILED (intended for startup)

        Enhanced version to clear ALL stale jobs aggressively on startup.
        This prevents old jobs from appearing in UI and blocking new operations.
        """
        app = self._get_app()
        if not app:
            return

        try:
            with app.app_context():
                from db import SystemJob, db
                from utils import now_utc

                # Reset all jobs stuck in RUNNING or SCHEDULED status
                stale = SystemJob.query.filter(SystemJob.status.in_([JobStatus.RUNNING, JobStatus.SCHEDULED])).all()

                # Also reset jobs that are very old (>1 day) regardless of status
                old_jobs_threshold = now_utc() - timedelta(days=1)
                old_jobs = SystemJob.query.filter(
                    SystemJob.started_at < old_jobs_threshold,
                    SystemJob.status.in_([JobStatus.RUNNING, JobStatus.SCHEDULED]),
                ).all()

                all_stale = list(set(stale + old_jobs))

                if all_stale:
                    logger.warning(f"Startup: Resetting {len(all_stale)} stale RUNNING/SCHEDULED jobs to FAILED.")

                    for j in all_stale:
                        logger.info(f"Startup: clearing job {j.job_id} ({j.job_type})")
                        j.status = JobStatus.FAILED
                        j.completed_at = now_utc()

                        # More detailed error message
                        age = now_utc() - j.started_at if j.started_at else timedelta(0)
                        j.error = f"Job reset during startup (was running for {str(age).split('.')[0]}). This usually means the container was restarted while the job was in progress."

                    db.session.commit()
                    logger.info(f"Startup: Completed cleanup of {len(all_stale)} stale jobs")
                else:
                    logger.info("Startup: No stale jobs found during cleanup")

                # Also reset in-memory state flags if we can find them
                try:
                    import state

                    state.is_titledb_update_running = False
                    state.scan_in_progress = False
                    # Additional reset for other state flags if they exist
                    if hasattr(state, "watcher"):
                        if hasattr(state.watcher, "_stop_health_check"):
                            state.watcher._stop_health_check.set()
                    logger.info("Startup: Reset in-memory state flags")
                except ImportError:
                    pass
                except Exception as e:
                    logger.warning(f"Startup: Failed to reset state flags: {e}")

        except Exception as e:
            logger.error(f"Error during JobTracker stale cleanup: {e}")
            import traceback

            traceback.print_exc()

    def _get_app(self):
        # 1. Stored app instance
        if self.app:
            return self.app

        # 2. current_app (if inside request/app context)
        try:
            from flask import current_app

            if current_app:
                return current_app
        except:
            pass

        # 3. Last resort fallback (rare)
        try:
            import app as main_app

            return main_app.app
        except:
            return None

    def _emit_update(self, job_id: str):
        """Emit job update to all connected clients"""
        if not self.emitter:
            return

        try:
            app = self._get_app()
            if not app:
                return

            with app.app_context():
                from db import SystemJob

                job = SystemJob.query.get(job_id)
                if job:
                    data = job.to_dict()
                    if hasattr(self.emitter, "emit"):
                        # standard socketio object
                        self.emitter.emit("job_update", data, namespace="/")
                    else:
                        # functional proxy (from socket_helper.py)
                        self.emitter("job_update", data)
        except Exception:
            # Silent fail for emitter, usually means socketio not ready or connection issue
            pass

    def register_job(self, job_type: str, metadata: Dict[str, Any] = None) -> str:
        """Register a new job in DB and return the job_id"""
        job_id = f"{job_type}_{uuid.uuid4().hex[:8]}"

        app = self._get_app()
        if not app:
            logger.error("Could not register job: No app context")
            return job_id

        try:
            with app.app_context():
                from db import db, SystemJob

                job = SystemJob(
                    job_id=job_id, job_type=job_type, status=JobStatus.SCHEDULED, metadata_json=metadata or {}
                )
                db.session.add(job)
                db.session.commit()

            logger.info(f"Registered job: {job_id} ({job_type})")
            self._emit_update(job_id)
        except Exception as e:
            logger.error(f"Failed to register job in DB: {e}")

        return job_id

    def start_job(self, job_id: str, job_type: str = None, message: str = ""):
        """Mark job as started in DB"""
        app = self._get_app()
        if not app:
            return

        try:
            with app.app_context():
                from db import db, SystemJob

                job = SystemJob.query.get(job_id)

                if not job and job_type:
                    # Legacy support/Implicit registration
                    job = SystemJob(job_id=job_id, job_type=job_type, metadata_json={})
                    db.session.add(job)

                if job:
                    job.status = JobStatus.RUNNING
                    job.started_at = now_utc()
                    job.progress_message = message
                    db.session.commit()
                    logger.info(f"Started job: {job_id}")

            self._emit_update(job_id)
        except Exception as e:
            logger.error(f"Failed to start job {job_id} in DB: {e}")

    def cancel_job(self, job_id: str):
        """Mark job as cancelled in memory and DB"""
        self.cancelled_jobs.add(job_id)

        app = self._get_app()
        if not app:
            return

        try:
            with app.app_context():
                from db import db, SystemJob

                job = SystemJob.query.get(job_id)
                if job:
                    if job.status not in [JobStatus.COMPLETED, JobStatus.FAILED]:
                        job.status = JobStatus.FAILED
                        job.completed_at = now_utc()
                        job.error = "Cancelled by user"
                        db.session.commit()
                        logger.info(f"Cancelled job: {job_id}")

            self._emit_update(job_id)
        except Exception as e:
            logger.error(f"Failed to cancel job {job_id} in DB: {e}")

    def is_cancelled(self, job_id: str) -> bool:
        """Check if job is marked as cancelled (check memory first, then DB)"""
        if job_id in self.cancelled_jobs:
            return True

        # Optional: check DB as fallback but this is what we want to avoid
        return False

    def update_progress(self, job_id: str, percent: int = 0, total: int = None, message: str = "", current: int = None):
        """
        Update job progress in DB and via WebSocket.
        Throttled to max 1 update per second to reduce server load.
        """
        import time

        now = time.time()

        # Calculate percent if total/current provided
        calc_percent = float(percent)
        if total is not None:
            total_val = float(total)
            current_val = float(current if current is not None else percent)
            calc_percent = round((current_val / total_val * 100) if total_val > 0 else 0, 1)

        # Check throttling
        last_time = self._last_update_time.get(job_id, 0)
        last_pct = self._last_progress.get(job_id, -1)

        # Throttling rule:
        # - Always allow if first update (last_time == 0)
        # - Always allow if 0% or 100%
        # - Always allow if message changed (some jobs only use messages)
        # - Otherwise, limit to 1.0s and at least 0.5% change
        is_first = last_time == 0
        is_critical = calc_percent <= 0 or calc_percent >= 100
        is_significant = abs(calc_percent - last_pct) >= 0.5
        time_passed = (now - last_time) >= 1.0

        if not (is_first or is_critical or (time_passed and is_significant)):
            return

        self._last_update_time[job_id] = now
        self._last_progress[job_id] = calc_percent

        app = self._get_app()
        if not app:
            return

        try:
            # 1. Persist to DB (best effort)
            try:
                with app.app_context():
                    from db import db, SystemJob

                    job = SystemJob.query.get(job_id)
                    if job:
                        job.progress_percent = calc_percent
                        if message:
                            job.progress_message = str(message)

                        # Prepare data for emission BEFORE commit
                        emit_data = job.to_dict()
                        db.session.commit()
            except Exception as e:
                if "locked" not in str(e).lower():
                    logger.error(f"DB error in update_progress: {e}")

            # 2. Emit update via WebSocket
            try:
                if "emit_data" not in locals():
                    emit_data = {
                        "id": job_id,
                        "type": "unknown",
                        "status": "running",
                        "progress": {"percent": calc_percent, "message": message or ""},
                    }

                if self.emitter:
                    if hasattr(self.emitter, "emit"):
                        self.emitter.emit("job_update", emit_data, namespace="/")
                    else:
                        self.emitter("job_update", emit_data)
            except Exception as emit_err:
                logger.debug(f"Failed to emit socket update: {emit_err}")

            # 3. Yield to other gevent co-routines
            try:
                import gevent

                gevent.sleep(0)
            except:
                pass

        except Exception as outer_e:
            logger.error(f"Unexpected error in update_progress: {outer_e}")

    def complete_job(self, job_id: str, result: Any = None):
        """Mark job as completed in DB"""
        app = self._get_app()
        if not app:
            return

        try:
            with app.app_context():
                from db import db, SystemJob

                job = SystemJob.query.get(job_id)
                if job:
                    if job_id in self.cancelled_jobs:
                        self.cancelled_jobs.remove(job_id)
                    job.status = JobStatus.COMPLETED
                    job.completed_at = now_utc()
                    if isinstance(result, dict):
                        job.result_json = result
                    else:
                        job.result_json = {"message": str(result)}
                    db.session.commit()
                    logger.info(f"Completed job: {job_id}")

            self._emit_update(job_id)
        except Exception as e:
            logger.error(f"Failed to complete job {job_id}: {e}")

    def fail_job(self, job_id: str, error: str):
        """Mark job as failed in DB"""
        app = self._get_app()
        if not app:
            return

        try:
            with app.app_context():
                from db import db, SystemJob

                job = SystemJob.query.get(job_id)
                if job:
                    if job_id in self.cancelled_jobs:
                        self.cancelled_jobs.remove(job_id)
                    job.status = JobStatus.FAILED
                    job.completed_at = now_utc()
                    job.error = error
                    db.session.commit()
                    logger.error(f"Failed job: {job_id} - {error}")

            self._emit_update(job_id)
        except Exception as e:
            logger.error(f"Failed to fail job {job_id}: {e}")

    def get_all_jobs(self) -> List[Dict]:
        """Return all jobs from DB"""
        app = self._get_app()
        if not app:
            return []

        try:
            with app.app_context():
                from db import SystemJob

                # Get last 24h jobs or all active ones
                cutoff = now_utc() - timedelta(hours=24)
                jobs = (
                    SystemJob.query.filter(
                        (SystemJob.status.in_([JobStatus.SCHEDULED, JobStatus.RUNNING]))
                        | (SystemJob.completed_at > cutoff)
                    )
                    .order_by(SystemJob.started_at.desc())
                    .all()
                )
                return [j.to_dict() for j in jobs]
        except Exception as e:
            logger.error(f"Failed to fetch jobs from DB: {e}")
            return []

    def get_active_jobs(self) -> List[Dict]:
        """Return only active jobs from DB"""
        app = self._get_app()
        if not app:
            return []

        try:
            with app.app_context():
                from db import SystemJob

                jobs = SystemJob.query.filter(SystemJob.status.in_([JobStatus.SCHEDULED, JobStatus.RUNNING])).all()
                return [j.to_dict() for j in jobs]
        except Exception as e:
            logger.error(f"Failed to fetch active jobs from DB: {e}")
            return []

    def get_job(self, job_id: str) -> Optional[Dict]:
        """Return a specific job from DB"""
        app = self._get_app()
        if not app:
            return None

        try:
            with app.app_context():
                from db import SystemJob

                job = SystemJob.query.get(job_id)
                return job.to_dict() if job else None
        except Exception as e:
            logger.error(f"Failed to fetch job {job_id} from DB: {e}")
            return None

    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Remove completed/failed jobs older than max_age_hours from DB"""
        app = self._get_app()
        if not app:
            return

        try:
            with app.app_context():
                from db import db, SystemJob

                cutoff = now_utc() - timedelta(hours=max_age_hours)
                SystemJob.query.filter(
                    (SystemJob.status.in_([JobStatus.COMPLETED, JobStatus.FAILED])) & (SystemJob.completed_at < cutoff)
                ).delete()
                db.session.commit()
        except Exception as e:
            logger.error(f"Failed to cleanup jobs in DB: {e}")


# Global singleton
job_tracker = JobTracker()
