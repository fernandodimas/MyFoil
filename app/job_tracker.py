from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import uuid
import logging

logger = logging.getLogger(__name__)

class JobType:
    LIBRARY_SCAN = 'library_scan'
    TITLEDB_UPDATE = 'titledb_update'
    METADATA_FETCH = 'metadata_fetch'
    FILE_IDENTIFICATION = 'file_identification'
    BACKUP = 'backup'
    CLEANUP = 'cleanup'
    OTHER = 'other'

class JobStatus:
    SCHEDULED = 'scheduled'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'

@dataclass
class JobState:
    """Internal state of a job"""
    job_id: str
    job_type: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: Dict[str, Any] = field(default_factory=lambda: {'percent': 0, 'message': ''})
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class JobTracker:
    """Singleton to track system jobs with database persistence for cross-process support"""
    
    def __init__(self):
        self.emitter = None
        self.app = None
    
    def init_app(self, app):
        """Initialize with Flask app instance"""
        self.app = app
        logger.debug("JobTracker initialized with app")

    def set_emitter(self, emitter):
        """Set the SocketIO emitter for real-time updates"""
        self.emitter = emitter
        logger.debug("JobTracker emitter set")

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
                    job_id=job_id,
                    job_type=job_type,
                    status=JobStatus.SCHEDULED,
                    metadata_json=metadata or {}
                )
                db.session.add(job)
                db.session.commit()
            
            logger.info(f"Registered job: {job_id} ({job_type})")
            self._emit_update(job_id)
        except Exception as e:
            logger.error(f"Failed to register job in DB: {e}")
            
        return job_id
    
    def start_job(self, job_id: str, job_type: str = None, message: str = ''):
        """Mark job as started in DB"""
        app = self._get_app()
        if not app: return

        try:
            with app.app_context():
                from db import db, SystemJob
                job = SystemJob.query.get(job_id)
                
                if not job and job_type:
                    # Legacy support/Implicit registration
                    job = SystemJob(
                        job_id=job_id,
                        job_type=job_type,
                        metadata_json={}
                    )
                    db.session.add(job)
                
                if job:
                    job.status = JobStatus.RUNNING
                    job.started_at = datetime.now()
                    job.progress_message = message
                    db.session.commit()
                    logger.info(f"Started job: {job_id}")
            
            self._emit_update(job_id)
        except Exception as e:
            logger.error(f"Failed to start job {job_id} in DB: {e}")
    
    def update_progress(self, job_id: str, percent: int = 0, total: int = None, message: str = '', current: int = None):
        """
        Update job progress in DB.
        Supports:
        - update_progress(job_id, percent)
        - update_progress(job_id, current, total, message)
        - update_progress(job_id, percent, current=x, total=y)
        """
        app = self._get_app()
        if not app: return

        try:
            with app.app_context():
                from db import db, SystemJob
                job = SystemJob.query.get(job_id)
                if job:
                    if total is not None:
                        # Calculation mode: (id, current, total) or (id, percent, current=x, total=y)
                        current_val = current if current is not None else percent
                        job.progress_percent = round((current_val / total * 100) if total > 0 else 0, 1)
                    else:
                        # Direct mode: (id, percent)
                        job.progress_percent = float(percent)
                    
                    if message:
                        job.progress_message = message
                    
                    db.session.commit()
            
            self._emit_update(job_id)
        except Exception as e:
            logger.error(f"Failed to update job progress for {job_id}: {e}")
    
    def complete_job(self, job_id: str, result: Any = None):
        """Mark job as completed in DB"""
        app = self._get_app()
        if not app: return

        try:
            with app.app_context():
                from db import db, SystemJob
                job = SystemJob.query.get(job_id)
                if job:
                    job.status = JobStatus.COMPLETED
                    job.completed_at = datetime.now()
                    if isinstance(result, dict):
                        job.result_json = result
                    else:
                        job.result_json = {'message': str(result)}
                    db.session.commit()
                    logger.info(f"Completed job: {job_id}")
            
            self._emit_update(job_id)
        except Exception as e:
            logger.error(f"Failed to complete job {job_id}: {e}")
    
    def fail_job(self, job_id: str, error: str):
        """Mark job as failed in DB"""
        app = self._get_app()
        if not app: return

        try:
            with app.app_context():
                from db import db, SystemJob
                job = SystemJob.query.get(job_id)
                if job:
                    job.status = JobStatus.FAILED
                    job.completed_at = datetime.now()
                    job.error = error
                    db.session.commit()
                    logger.error(f"Failed job: {job_id} - {error}")
            
            self._emit_update(job_id)
        except Exception as e:
            logger.error(f"Failed to fail job {job_id}: {e}")
    
    def get_all_jobs(self) -> List[Dict]:
        """Return all jobs from DB"""
        app = self._get_app()
        if not app: return []

        try:
            with app.app_context():
                from db import SystemJob
                # Get last 24h jobs or all active ones
                cutoff = datetime.now() - timedelta(hours=24)
                jobs = SystemJob.query.filter(
                    (SystemJob.status.in_([JobStatus.SCHEDULED, JobStatus.RUNNING])) |
                    (SystemJob.completed_at > cutoff)
                ).order_by(SystemJob.started_at.desc()).all()
                return [j.to_dict() for j in jobs]
        except Exception as e:
            logger.error(f"Failed to fetch jobs from DB: {e}")
            return []
    
    def get_active_jobs(self) -> List[Dict]:
        """Return only active jobs from DB"""
        app = self._get_app()
        if not app: return []

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
        if not app: return None

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
        if not app: return

        try:
            with app.app_context():
                from db import db, SystemJob
                cutoff = datetime.now() - timedelta(hours=max_age_hours)
                SystemJob.query.filter(
                    (SystemJob.status.in_([JobStatus.COMPLETED, JobStatus.FAILED])) &
                    (SystemJob.completed_at < cutoff)
                ).delete()
                db.session.commit()
        except Exception as e:
            logger.error(f"Failed to cleanup jobs in DB: {e}")

# Global singleton
job_tracker = JobTracker()
