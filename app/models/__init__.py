"""
MyFoil Database Models package.
Contains all SQLAlchemy ORM models.
"""

from .libraries import Libraries
from .files import Files
from .titles import Titles
from .titledb_cache import TitleDBCache, TitleDBVersions, TitleDBDLCs
from .apps import Apps
from .users import User, ApiToken
from .tags import Tag, TitleTag
from .wishlist import Wishlist, WishlistIgnore
from .webhooks import Webhook
from .metadata import TitleMetadata, MetadataFetchLog
from .jobs import SystemJob
from .activity import ActivityLog

__all__ = [
    # Library management
    "Libraries",
    "Files",
    # Title management
    "Titles",
    "TitleDBCache",
    "TitleDBVersions",
    "TitleDBDLCs",
    "Apps",
    # User management
    "User",
    "ApiToken",
    # Tags
    "Tag",
    "TitleTag",
    # Wishlist
    "Wishlist",
    "WishlistIgnore",
    # Webhooks
    "Webhook",
    # Metadata
    "TitleMetadata",
    "MetadataFetchLog",
    # Jobs
    "SystemJob",
    # Activity
    "ActivityLog",
]
