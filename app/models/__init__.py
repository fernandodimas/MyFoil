"""
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

from .libraries import Libraries
from .files import Files
from .titles import Titles
from .titledbcache import TitleDBCache
from .titledbversions import TitleDBVersions
from .titledbdlcs import TitleDBDLCs
from .apps import Apps, app_files
from .user import User
from .apitoken import ApiToken
from .tag import Tag
from .titletag import TitleTag
from .wishlist import Wishlist
from .wishlistignore import WishlistIgnore
from .webhook import Webhook
from .titlemetadata import TitleMetadata
from .metadatafetchlog import MetadataFetchLog
from .systemjob import SystemJob
from .activitylog import ActivityLog

__all__ = [
    "Libraries",
    "Files",
    "Titles",
    "TitleDBCache",
    "TitleDBVersions",
    "TitleDBDLCs",
    "Apps",
    "app_files",
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
