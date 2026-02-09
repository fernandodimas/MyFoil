
Repositories package
Phase 3.1: Database refactoring - Separate database queries from models

Each repository encapsulates database operations for a model:
- files_repository.py
- titles_repository.py
- etc.

Usage:
    from repositories.files_repository import FilesRepository
    files = FilesRepository.get_all()
