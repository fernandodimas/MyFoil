"""
Jobs package - Tarefas em background e agendamento
"""
import importlib.util

# Load update_titledb_job from the parent jobs.py file
_jobs_spec = importlib.util.spec_from_file_location("jobs_module", __file__.replace('/__init__.py', '/../jobs.py'))
_jobs_module = importlib.util.module_from_spec(_jobs_spec)
_jobs_spec.loader.exec_module(_jobs_module)

update_titledb_job = _jobs_module.update_titledb_job

__all__ = ['update_titledb_job']