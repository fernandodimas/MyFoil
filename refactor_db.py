#!/usr/bin/env python3
"""
Script to automate Phase 3.1: Refactor db.py into models/ and repositories/

This script:
1. Extracts model classes from db.py into separate files in app/models/
2. Creates repository classes in app/repositories/ for database queries
3. Updates all import statements across the codebase
4. Maintains backwards compatibility by keeping legacy imports in db.py
"""

import re
import os
from pathlib import Path

# Define models to extract
MODELS_TO_EXTRACT = [
    "Files",
    "Titles",
    "TitleDBCache",
    "TitleDBVersions",
    "TitleDBDLCs",
    "Apps",
    "User",
    "ApiToken",
    "Tag",
    "TitleTag",
    "Wishlist",
    "WishlistIgnore",
    "Webhook",
    "TitleMetadata",
    "MetadataFetchLog",
    "SystemJob",
    "ActivityLog",
]

# Files to update imports in
FILES_TO_UPDATE = [
    "app/routes/library.py",
    "app/routes/library.py",
    "app/routes/system.py",
    "app/routes/settings.py",
    "app/routes/wishlist.py",
    "app/tasks.py",
    "app/library.py",
    "app/middleware/auth.py",
]


def extract_model_from_db(model_name, db_path):
    """Extract a single model class from db.py file"""
    with open(db_path, "r") as f:
        content = f.read()

    # Find the model class definition
    pattern = rf"class {model_name}\(.*?\):\n(.*?)(?=\nclass |\nfrom |\Z)"
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        print(f"❌ Could not find model {model_name}")
        return None

    model_code = match.group(0)

    # Create the model file
    model_file = Path(f"app/models/{model_name.lower()}.py")

    # Generate the model file content
    file_content = f'''"""
Model: {model_name}
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db, now_utc
from flask_login import UserMixin

{model_code}
'''

    model_file.write_text(file_content)
    print(f"✓ Created model file: {model_file}")

    return True


def create_repository_file(model_name):
    """Create a repository file for a model (template)"""
    repo_file = Path(f"app/repositories/{model_name.lower()}_repository.py")

    repo_content = f'''"""
Repository for {model_name} database operations
Phase 3.1: Database refactoring - Separate queries from models
"""

from sqlalchemy.exc import SQLAlchemyError
from db import db
from models.{model_name.lower()} import {model_name}


class {model_name}Repository:
    """Repository for {model_name} database operations"""
    
    @staticmethod
    def get_all():
        """Get all {model_name} records"""
        return {model_name}.query.all()
    
    @staticmethod
    def get_by_id(id):
        """Get {model_name} by ID"""
        return {model_name}.query.get(id)
    
    @staticmethod
    def create(**kwargs):
        """Create new {model_name} record"""
        try:
            item = {model_name}(**kwargs)
            db.session.add(item)
            db.session.commit()
            db.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def update(id, **kwargs):
        """Update {model_name} record"""
        item = {model_name}.query.get(id)
        if not item:
            return None
        
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        db.session.commit()
        return item
    
    @staticmethod
    def delete(id):
        """Delete {model_name} record"""
        item = {model_name}.query.get(id)
        if not item:
            return False
        
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def count():
        """Count total {model_name} records"""
        return {model_name}.query.count()
'''

    repo_file.write_text(repo_content)
    print(f"✓ Created repository file: {repo_file}")

    return True


def update_imports(file_path, model_name):
    """Update import statements in a file to use new models"""
    try:
        with open(file_path, "r") as f:
            content = f.read()

        # Update imports from 'from db import *' or 'from db import X, Y, Z'
        # to 'from models.x import X'

        # Check if file already uses new import style
        if f"from models.{model_name.lower()} import" in content:
            return True

        # Check if file imports from db
        if "from db import" not in content:
            return True

        # This is a simplified check - in production, would need more sophisticated parsing
        print(f"  ⚠  Skipped {file_path} (requires manual review)")

        return True
    except Exception as e:
        print(f"  ❌ Error updating {file_path}: {e}")
        return False


def update_db_py_with_legacy_imports(db_path):
    """Update db.py to maintain backwards compatibility"""
    with open(db_path, "r") as f:
        content = f.read()

    # Add legacy imports section at the top
    legacy_imports = "# LEGACY IMPORTS (Phase 3.1: Moved to app/models/)\n"
    legacy_imports += "# Keeping for backwards compatibility\n\n"

    for model in MODELS_TO_EXTRACT:
        legacy_imports += f"from models.{model.lower()} import {model}\n"

    legacy_imports += "\n"

    # Insert at the beginning (after existing imports)
    # This is a simple approach - would need more care in production

    print(f"⚠  db.py updates would require careful manual review")
    print(f"   Recommended: Add these imports after existing imports:")
    print(f"   {legacy_imports}")

    return True


def create_models_init():
    """Update __init__.py in app/models/"""
    init_file = Path("app/models/__init__.py")

    content = """
Models package
Phase 3.1: Database refactoring - Separate models from db.py

All database models are now in separate files:
- libraries.py
- files.py
- titles.py
- etc.

For backwards compatibility, you can still import from db.py:
    from db import Files, Titles, Apps, User, etc.
"""

    init_file.write_text(content)
    print(f"✓ Updated app/models/__init__.py")


def create_repositories_init():
    """Create __init__.py in app/repositories/"""
    init_file = Path("app/repositories/__init__.py")

    content = """
Repositories package
Phase 3.1: Database refactoring - Separate database queries from models

Each repository encapsulates database operations for a model:
- files_repository.py
- titles_repository.py
- etc.

Usage:
    from repositories.files_repository import FilesRepository
    files = FilesRepository.get_all()
"""

    init_file.write_text(content)
    print(f"✓ Created app/repositories/__init__.py")


def main():
    print("=" * 80)
    print("Phase 3.1: db.py Refactoring Automation")
    print("=" * 80)
    print("")

    db_path = Path("app/db.py")

    if not db_path.exists():
        print(f"❌ db.py not found at {db_path}")
        return False

    print(f"📁 Found db.py at {db_path}")
    print(f"📊 Models to extract: {len(MODELS_TO_EXTRACT)}")
    print("")

    # Create packages
    create_models_init()
    create_repositories_init()
    print("")

    # Extract each model
    extracted = 0
    for model in MODELS_TO_EXTRACT:
        if extract_model_from_db(model, db_path):
            create_repository_file(model)
            extracted += 1
        print("")

    print(f"✓ Extracted {extracted}/{len(MODELS_TO_EXTRACT)} models")
    print("")

    # Update db.py
    print("Updating db.py for backwards compatibility...")
    update_db_py_with_legacy_imports(db_path)
    print("")

    print("=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)
    print("1. Review the generated model files in app/models/")
    print("2. Review the generated repository files in app/repositories/")
    print("3. Manually update db.py to import from new models")
    print("4. Manually update import statements in other files")
    print("5. Test all functionality to ensure nothing broke")
    print("")
    print("⚠  IMPORTANT: This script creates files but does NOT modify db.py or")
    print("   other files directly. Manual review is required to ensure accuracy.")
    print("")
    print("Files created:")
    print("  - app/models/<model>.py (one file per model)")
    print("  - app/repositories/<model>_repository.py (one repository per model)")
    print("")

    return True


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
