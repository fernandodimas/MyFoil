from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import threading
import uuid
import logging

logger = logging.getLogger(__name__)

@dataclass
class JobStatus:
    """Represents the status of a background job"""
    job_id: str
    job_type: str  # 'library_scan', 'titledb_update', 'identify', 'metadata_fetch', etc
    status: str  # 'scheduled', 'running', 'completed', 'failed'
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: Optional[Dict[str, Any]] = None  # {'current': 10, 'total': 100, 'message': '...'}
    result: Optional[Dict[str, Any]] = None  # {'files_added': 5, 'files_identified': 3}
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class JobTracker:
    """Singleton to track system jobs with real-time updates via SocketIO"""
    
    def __init__(self):
        self.jobs: Dict[str, JobStatus] = {}
        self.lock = threading.Lock()
        self.emitter = None
    
    def set_emitter(self, emitter):
        """Set the SocketIO emitter for real-time updates"""
        self.emitter = emitter
        logger.debug("JobTracker emitter set")

    def _emit_update(self, job_id: str):
        """Emit job update to all connected clients"""
        if self.emitter and job_id in self.jobs:
            try:
                job = self.jobs[job_id]
                self.emitter.emit('job_update', {
                    'id': job.job_id,
                    'type': job.job_type,
                    'status': job.status,
                    'progress': job.progress
                }, namespace='/')
            except Exception as e:
                logger.warning(f"Failed to emit job update: {e}")

    def register_job(self, job_type: str, metadata: Dict[str, Any] = None) -> str:
        """Register a new job and return the job_id"""
        job_id = f"{job_type}_{uuid.uuid4().hex[:8]}"
        
        with self.lock:
            job = JobStatus(
                job_id=job_id,
                job_type=job_type,
                status='scheduled',
                metadata=metadata or {}
            )
            self.jobs[job_id] = job
        
        logger.debug(f"Registered job: {job_id} ({job_type})")
        self._emit_update(job_id)
        return job_id
    
    def start_job(self, job_id: str):
        """Mark job as started"""
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].status = 'running'
                self.jobs[job_id].started_at = datetime.now()
                logger.debug(f"Started job: {job_id}")
        self._emit_update(job_id)
    
    def update_progress(self, job_id: str, current: int, total: int, message: str = ''):
        """Update job progress"""
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].progress = {
                    'current': current,
                    'total': total,
                    'message': message,
                    'percent': round((current / total * 100) if total > 0 else 0, 1)
                }
        self._emit_update(job_id)
    
    def complete_job(self, job_id: str, result: Dict[str, Any] = None):
        """Mark job as completed"""
        with self.lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.status = 'completed'
                job.completed_at = datetime.now()
                job.result = result or {}
                logger.debug(f"Completed job: {job_id}")
        self._emit_update(job_id)
    
    def fail_job(self, job_id: str, error: str):
        """Mark job as failed"""
        with self.lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.status = 'failed'
                job.completed_at = datetime.now()
                job.error = error
                logger.error(f"Failed job: {job_id} - Error: {error}")
        self._emit_update(job_id)
    
    def get_all_jobs(self) -> List[JobStatus]:
        """Return all jobs"""
        with self.lock:
            return list(self.jobs.values())
    
    def get_active_jobs(self) -> List[JobStatus]:
        """Return only active jobs"""
        with self.lock:
            return [j for j in self.jobs.values() if j.status in ['scheduled', 'running']]
    
    def get_job(self, job_id: str) -> Optional[JobStatus]:
        """Return a specific job"""
        with self.lock:
            return self.jobs.get(job_id)
    
    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Remove completed/failed jobs older than max_age_hours"""
        with self.lock:
            cutoff = datetime.now() - timedelta(hours=max_age_hours)
            self.jobs = {
                jid: job for jid, job in self.jobs.items()
                if job.status in ['scheduled', 'running'] or 
                   (job.completed_at and job.completed_at > cutoff)
            }
            logger.debug("Cleaned up old jobs from tracker")

# Global singleton
job_tracker = JobTracker()
