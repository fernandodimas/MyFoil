"""
Job Tracker - Sistema de rastreamento de operações em background
"""
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
import threading
import copy
import json
import os
import redis

class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"

class JobType(Enum):
    LIBRARY_SCAN = "library_scan"
    TITLEDB_UPDATE = "titledb_update"
    METADATA_FETCH = "metadata_fetch"
    FILE_IDENTIFICATION = "file_identification"
    BACKUP = "backup"
    CLEANUP = "cleanup"

@dataclass
class Job:
    id: str
    type: JobType
    status: JobStatus
    progress: int  # 0-100
    total: Optional[int] = None
    current: Optional[int] = None
    message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    
    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type.value,
            'status': self.status.value,
            'progress': self.progress,
            'total': self.total,
            'current': self.current,
            'message': self.message,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error': self.error
        }
    
    @classmethod
    def from_dict(cls, data):
        # Handle cleanup of None/null values if necessary
        return cls(
            id=data['id'],
            type=JobType(data['type']),
            status=JobStatus(data['status']),
            progress=int(data['progress']),
            total=data.get('total'),
            current=data.get('current'),
            message=data.get('message', ''),
            started_at=datetime.fromisoformat(data['started_at']) if data.get('started_at') else None,
            completed_at=datetime.fromisoformat(data['completed_at']) if data.get('completed_at') else None,
            error=data.get('error')
        )

class JobTracker:
    """Singleton para rastrear jobs em background (Redis-backed)"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_redis()
        return cls._instance
    
    def _init_redis(self):
        self.redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.use_redis = False
        self._local_jobs = {}
        self._local_history = []
        self._emitter = None
        self.redis = None
        self._last_emit_time = {} # Rate limiting per job
        
        self._connect_redis()
    
    def _connect_redis(self):
        """Attempt to connect to Redis with retries"""
        try:
            url = os.environ.get("REDIS_URL", self.redis_url)
            # Use a longer timeout for the initial connection
            self.redis = redis.from_url(url, socket_timeout=10, socket_connect_timeout=10)
            self.redis.ping()
            self.use_redis = True
            logger.info(f"JobTracker: Connected to Redis at {url}")
            # Auto-cleanup stale jobs on initialization
            self._cleanup_stale_jobs()
            return True
        except Exception as e:
            # Check if we are in an environment that REQUIRES redis
            if os.environ.get("REDIS_URL"):
                logger.error(f"JobTracker: Redis connection failed despite REDIS_URL being set. Task tracking will be local and invisible to other processes! Error: {e}")
            else:
                logger.warning(f"JobTracker: Redis not available. {e}")
            self.use_redis = False
            return False

    def check_connection(self):
        """Ensure connection is still alive, try to reconnect if not"""
        if not self.use_redis:
            if os.environ.get("REDIS_URL"):
                return self._connect_redis()
            return False
            
        try:
            self.redis.ping()
            return True
        except:
            return self._connect_redis()

    def set_emitter(self, emitter_func):
        """Set a function to emit socket updates. Emitter should take (event_name, data)"""
        self._emitter = emitter_func

    def _emit_update(self, job_id: str = None, force: bool = False):
        """Helper to emit job status update to all clients with rate limiting"""
        if not self._emitter:
            return

        import time
        now = time.time()
        
        # Rate limit: 1 update per 0.5 seconds per job, unless forced
        if job_id and not force:
            last_time = self._last_emit_time.get(job_id, 0)
            if now - last_time < 0.5:
                return
            self._last_emit_time[job_id] = now

        try:
            self._emitter('job_update', self.get_status())
        except Exception as e:
            # Silently catch socket errors in workers
            pass

    def _cleanup_stale_jobs(self, max_age_seconds: int = 3600):
        """Clean up jobs stuck in RUNNING state for more than max_age_seconds"""
        if not self.use_redis:
            return
        
        try:
            active_ids = self.redis.smembers("jobs:active")
            now = datetime.now()
            cleaned = 0
            
            for jid in active_ids:
                if isinstance(jid, bytes):
                    jid = jid.decode()
                
                job = self.get_job(jid)
                if job and job.status == JobStatus.RUNNING:
                    is_stale = False
                    if job.started_at:
                        age = (now - job.started_at).total_seconds()
                        if age > max_age_seconds:
                            is_stale = True
                    else:
                        is_stale = True 
                        
                    if is_stale:
                        job.status = JobStatus.CANCELLED
                        job.error = "Job timed out or orphaned"
                        job.completed_at = now
                        self._save_job(job, emit=False)
                        cleaned += 1
            
            if cleaned > 0:
                logger.info(f"JobTracker: Cleaned up {cleaned} stale job(s)")
                self._emit_update(force=True)
        except Exception as e:
            logger.error(f"JobTracker: Error during cleanup: {e}")
    
    def cleanup_all_active_jobs(self):
        """Manually clear all active jobs (useful for debugging/maintenance)"""
        self.check_connection()
        
        count = 0
        if self.use_redis:
            try:
                active_ids = list(self.redis.smembers("jobs:active"))
                for jid in active_ids:
                    if isinstance(jid, bytes):
                        jid = jid.decode()
                    job = self.get_job(jid)
                    if job:
                        job.status = JobStatus.CANCELLED
                        job.error = "Manually cleared"
                        job.completed_at = datetime.now()
                        self._save_job(job, emit=False)
                count = len(active_ids)
                if count == 0:
                     self.redis.delete("jobs:active")
            except Exception as e:
                logger.error(f"JobTracker: Error manually cleaning: {e}")
        else:
            count = len(self._local_jobs)
            self._local_jobs.clear()
        
        self._emit_update(force=True)
        return count

    def _save_job(self, job: Job, emit: bool = True):
        # Always try to use Redis if we have a URL
        if not self.use_redis and os.environ.get("REDIS_URL"):
            self._connect_redis()

        if self.use_redis:
            try:
                key = f"job:{job.id}"
                expiry = 3600 if job.status == JobStatus.RUNNING else 86400
                self.redis.set(key, json.dumps(job.to_dict()), ex=expiry)
                
                if job.status == JobStatus.RUNNING:
                    self.redis.sadd("jobs:active", job.id)
                else:
                    self.redis.srem("jobs:active", job.id)
                    self.redis.lpush("jobs:history", json.dumps(job.to_dict()))
                    self.redis.ltrim("jobs:history", 0, 49)
            except Exception as e:
                logger.error(f"JobTracker: Failed to save to Redis: {e}")
                self.use_redis = False
        else:
            self._local_jobs[job.id] = job
            if job.status != JobStatus.RUNNING:
                if job.id in self._local_jobs:
                    del self._local_jobs[job.id]
                self._local_history.insert(0, job)
                self._local_history = self._local_history[:50]
        
        if emit:
            # Force emit if job completed or failed
            self._emit_update(job.id, force=(job.status != JobStatus.RUNNING))

    def start_job(self, job_id: str, job_type: JobType, message: str = "") -> Job:
        self.check_connection()
        
        job = Job(
            id=job_id,
            type=job_type,
            status=JobStatus.RUNNING,
            progress=0,
            message=message,
            started_at=datetime.now()
        )
        self._save_job(job)
        return job
    
    def update_progress(self, job_id: str, progress: int, current: int = None, total: int = None, message: str = None):
        job = self.get_job(job_id)
        if job:
            job.progress = min(100, max(0, progress))
            if current is not None:
                job.current = current
            if total is not None:
                job.total = total
            if message is not None:
                job.message = message
            self._save_job(job)
    
    def complete_job(self, job_id: str, message: str = "Completed"):
        job = self.get_job(job_id)
        if job:
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.message = message
            job.completed_at = datetime.now()
            self._save_job(job)
    
    def fail_job(self, job_id: str, error: str):
        job = self.get_job(job_id)
        if job:
            job.status = JobStatus.ERROR
            job.error = error
            job.completed_at = datetime.now()
            self._save_job(job)
            
    def get_job(self, job_id: str) -> Optional[Job]:
        if self.use_redis:
            data = self.redis.get(f"job:{job_id}")
            if data:
                return Job.from_dict(json.loads(data))
            return None
        return self._local_jobs.get(job_id)

    def get_status(self) -> dict:
        if self.use_redis:
            active_ids = self.redis.smembers("jobs:active")
            active_jobs = []
            for jid in active_ids:
                if isinstance(jid, bytes):
                    jid = jid.decode()
                job = self.get_job(jid)
                if job:
                    active_jobs.append(job.to_dict())
            
            history_data = self.redis.lrange("jobs:history", 0, 49)
            history_jobs = [json.loads(d) for d in history_data]
            
            return {
                'active': active_jobs,
                'history': history_jobs,
                'has_active': len(active_jobs) > 0
            }
        else:
            return {
                'active': [j.to_dict() for j in self._local_jobs.values()],
                'history': [j.to_dict() for j in self._local_history],
                'has_active': len(self._local_jobs) > 0
            }

# Singleton global
job_tracker = JobTracker()
