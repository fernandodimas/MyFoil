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
    """Singleton to track system jobs with real-time updates via SocketIO"""
    
    def __init__(self):
        self.jobs: Dict[str, JobState] = {}
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
            job = JobState(
                job_id=job_id,
                job_type=job_type,
                status=JobStatus.SCHEDULED,
                metadata=metadata or {}
            )
            self.jobs[job_id] = job
        
        logger.debug(f"Registered job: {job_id} ({job_type})")
        self._emit_update(job_id)
        return job_id
    
    def start_job(self, job_id: str, job_type: str = None, message: str = ''):
        """
        Mark job as started. 
        Supports legacy call signature: start_job(id, type, msg)
        """
        with self.lock:
            if job_id not in self.jobs and job_type:
                # Legacy support: if job wasn't registered, create it now
                self.jobs[job_id] = JobState(
                    job_id=job_id,
                    job_type=job_type,
                    status=JobStatus.RUNNING,
                    started_at=datetime.now(),
                    progress={'percent': 0, 'message': message}
                )
            elif job_id in self.jobs:
                self.jobs[job_id].status = JobStatus.RUNNING
                self.jobs[job_id].started_at = datetime.now()
                if message:
                    self.jobs[job_id].progress['message'] = message
                logger.debug(f"Started job: {job_id}")
        self._emit_update(job_id)
    
    def update_progress(self, job_id: str, percent: int, total: int = None, message: str = ''):
        """
        Update job progress.
        Supports:
        - update_progress(job_id, percent)
        - update_progress(job_id, current, total, message)
        """
        with self.lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                if total is not None:
                    # Legacy signature: (id, current, total, message)
                    current = percent
                    job.progress = {
                        'current': current,
                        'total': total,
                        'message': message,
                        'percent': round((current / total * 100) if total > 0 else 0, 1)
                    }
                else:
                    # New signature: (id, percent)
                    job.progress['percent'] = percent
                    if message:
                        job.progress['message'] = message
        self._emit_update(job_id)
    
    def complete_job(self, job_id: str, result: Any = None):
        """Mark job as completed"""
        with self.lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now()
                if isinstance(result, dict):
                    job.result = result
                else:
                    job.result = {'message': str(result)}
                logger.debug(f"Completed job: {job_id}")
        self._emit_update(job_id)
    
    def fail_job(self, job_id: str, error: str):
        """Mark job as failed"""
        with self.lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.status = JobStatus.FAILED
                job.completed_at = datetime.now()
                job.error = error
                logger.error(f"Failed job: {job_id} - Error: {error}")
        self._emit_update(job_id)
    
    def get_all_jobs(self) -> List[JobState]:
        """Return all jobs"""
        with self.lock:
            return list(self.jobs.values())
    
    def get_active_jobs(self) -> List[JobState]:
        """Return only active jobs"""
        with self.lock:
            return [j for j in self.jobs.values() if j.status in [JobStatus.SCHEDULED, JobStatus.RUNNING]]
    
    def get_job(self, job_id: str) -> Optional[JobState]:
        """Return a specific job"""
        with self.lock:
            return self.jobs.get(job_id)
    
    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Remove completed/failed jobs older than max_age_hours"""
        with self.lock:
            cutoff = datetime.now() - timedelta(hours=max_age_hours)
            self.jobs = {
                jid: job for jid, job in self.jobs.items()
                if job.status in [JobStatus.SCHEDULED, JobStatus.RUNNING] or 
                   (job.completed_at and job.completed_at > cutoff)
            }
            logger.debug("Cleaned up old jobs from tracker")

# Global singleton
job_tracker = JobTracker()
