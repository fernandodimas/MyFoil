"""
Model: SystemJob
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db, now_utc
from flask_login import UserMixin

class SystemJob(db.Model):
    """Persistent tracking for system background jobs (Shared between Flask/Celery)"""

    __tablename__ = "system_jobs"

    job_id = db.Column(db.String(50), primary_key=True)
    job_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # 'scheduled', 'running', 'completed', 'failed'

    # Progress
    progress_percent = db.Column(db.Float, default=0.0)
    progress_message = db.Column(db.String(255))

    # Data
    result_json = db.Column(db.JSON)
    metadata_json = db.Column(db.JSON)
    error = db.Column(db.Text)

    # Timestamps
    started_at = db.Column(db.DateTime, default=now_utc)
    completed_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.job_id,
            "type": self.job_type,
            "status": self.status,
            "progress": {"percent": self.progress_percent, "message": self.progress_message},
            "result": self.result_json,
            "metadata": self.metadata_json,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


