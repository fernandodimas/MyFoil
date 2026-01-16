"""
Background Jobs - Tarefas em background e agendamento
Versão simplificada sem dependência do APScheduler
"""
import logging

logger = logging.getLogger('main')

class JobScheduler:
    """Gerenciador de tarefas em background (versão simplificada)"""

    def __init__(self):
        self.app = None
        self._jobs_registered = False
        self._running = False

    def init_app(self, app):
        """Inicializar scheduler com a aplicação Flask"""
        self.app = app
        self._register_jobs(app)
        self._start_scheduler()
        logger.info("Job scheduler initialized (simple version without APScheduler)")

    def _register_jobs(self, app):
        """Registrar todas as tarefas agendadas"""
        if self._jobs_registered:
            return

        # Nesta versão simplificada, as tarefas são registradas mas
        # não são agendadas automaticamente. Elas podem ser executadas manualmente.
        self._jobs_registered = True
        logger.info("Background jobs registered (manual execution only)")

    def add_job(self, job_id, func, **kwargs):
        """Adicionar tarefa dinâmica (não implementada nesta versão)"""
        logger.warning(f"Dynamic job scheduling not implemented in simple version: {job_id}")

    def run_update_titledb_job(self):
        """Executar tarefa de atualização do TitleDB manualmente"""
        try:
            from app import update_titledb_job
            with self.app.app_context():
                update_titledb_job()
            logger.info("TitleDB update job executed manually")
        except Exception as e:
            logger.error(f"Error running TitleDB update job: {e}")

    def run_scan_library_job(self):
        """Executar tarefa de scan da biblioteca manualmente"""
        try:
            from app import scan_library_job
            with self.app.app_context():
                scan_library_job()
            logger.info("Library scan job executed manually")
        except Exception as e:
            logger.error(f"Error running library scan job: {e}")

    def run_backup_job(self):
        """Executar tarefa de backup automático manualmente"""
        try:
            from app import create_automatic_backup
            with self.app.app_context():
                create_automatic_backup()
            logger.info("Backup job executed manually")
        except Exception as e:
            logger.error(f"Error running backup job: {e}")

    def _start_scheduler(self):
        """Iniciar scheduler simplificado"""
        self._running = True
        logger.info("Simple scheduler started (no automatic scheduling)")

    def shutdown(self):
        """Encerrar scheduler"""
        self._running = False
        logger.info("Job scheduler shutdown")
