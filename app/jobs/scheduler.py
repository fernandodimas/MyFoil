"""
Background Jobs - Tarefas em background e agendamento
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import logging

logger = logging.getLogger('main')

class JobScheduler:
    """Gerenciador de tarefas em background"""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self._jobs_registered = False

    def init_app(self, app):
        """Inicializar scheduler com a aplicação Flask"""
        self.scheduler.init_app(app)
        self._register_jobs(app)
        self.scheduler.start()
        logger.info("Job scheduler initialized")

    def _register_jobs(self, app):
        """Registrar todas as tarefas agendadas"""
        if self._jobs_registered:
            return

        # TitleDB update job (every 24 hours)
        self.scheduler.add_job(
            func=self._update_titledb_job,
            trigger=IntervalTrigger(hours=24),
            id='update_titledb',
            name='Update TitleDB',
            args=[app]
        )

        # Library scan job (every 24 hours, 5 min after TitleDB update)
        self.scheduler.add_job(
            func=self._scan_library_job,
            trigger=IntervalTrigger(hours=24, start_date=datetime.now() + timedelta(minutes=5)),
            id='scan_library',
            name='Scan Library',
            args=[app]
        )

        # Automatic backup (daily at 3 AM)
        self.scheduler.add_job(
            func=self._create_backup_job,
            trigger=CronTrigger(hour=3, minute=0),
            id='daily_backup',
            name='Daily Backup',
            args=[app]
        )

        self._jobs_registered = True
        logger.info("Background jobs registered")

    def add_job(self, job_id, func, **kwargs):
        """Adicionar tarefa dinâmica"""
        self.scheduler.add_job(id=job_id, func=func, **kwargs)

    def _update_titledb_job(self, app):
        """Tarefa de atualização do TitleDB"""
        from app import update_titledb_job
        with app.app_context():
            update_titledb_job()

    def _scan_library_job(self, app):
        """Tarefa de scan da biblioteca"""
        from app import scan_library_job
        with app.app_context():
            scan_library_job()

    def _create_backup_job(self, app):
        """Tarefa de backup automático"""
        from app import create_automatic_backup
        with app.app_context():
            create_automatic_backup()

    def shutdown(self):
        """Encerrar scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Job scheduler shutdown")