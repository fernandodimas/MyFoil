"""Service to manage precomputed per-user per-title flags.

This module provides a simple API to compute and upsert flags into the
`user_title_flags` table created by the migration. It's used to speed up
server-side filtering for dlc/redundant queries by avoiding JSON parsing
and heavy TitleDB operations on every request.
"""

from db import db
import datetime
from repositories.wishlistignore_repository import get_flattened_ignores_for_user
import titles as titles_lib
from sqlalchemy.dialects.postgresql import insert
from constants import APP_TYPE_UPD, APP_TYPE_DLC


def compute_flags_for_user_title(user_id, title_id, title_apps):
    # title_apps: list of app dicts as used elsewhere
    ignores = get_flattened_ignores_for_user(user_id).get(title_id, {})
    ignored_dlcs = set(k.upper() for k in ignores.get("dlcs", []))

    # compute possible dlcs from TitleDB (cheap cached calls)
    try:
        dlcs = titles_lib.get_all_existing_dlc(title_id) or []
    except Exception:
        dlcs = []

    _DLC_TYPES = (APP_TYPE_DLC, "dlc", "DLC")
    owned_dlc_ids = set(
        [a.get("app_id", "").upper() for a in title_apps if a.get("app_type") in _DLC_TYPES and a.get("owned")]
    )

    has_non_ignored_dlcs = False
    for d in dlcs:
        du = d.upper()
        if du not in owned_dlc_ids and du not in ignored_dlcs:
            has_non_ignored_dlcs = True
            break

    # updates
    try:
        versions = titles_lib.get_all_existing_versions(title_id) or []
    except Exception:
        versions = []

    _UPD_TYPES = (APP_TYPE_UPD, "upd", "UPD", "UPDATE")
    owned_versions = set(
        int(a.get("app_version") or 0) for a in title_apps if a.get("app_type") in _UPD_TYPES and a.get("owned")
    )
    current_owned_version = max(owned_versions) if owned_versions else 0

    has_non_ignored_updates = False
    for vinfo in versions:
        v = int(vinfo.get("version") or 0)
        if v <= current_owned_version:
            continue
        # If there's an available version > owned_version that we don't have, mark as pending
        has_non_ignored_updates = True
        break

    # redundant: owned update apps with version lower than max that are not ignored
    has_non_ignored_redundant = False
    owned_update_apps = [a for a in title_apps if a.get("app_type") in _UPD_TYPES and a.get("owned")]
    if len(owned_update_apps) > 1:
        # If we have multiple update files, the old ones are effectively redundant
        has_non_ignored_redundant = True

    return {
        "has_non_ignored_dlcs": has_non_ignored_dlcs,
        "has_non_ignored_updates": has_non_ignored_updates,
        "has_non_ignored_redundant": has_non_ignored_redundant,
    }


def upsert_user_title_flags(user_id, title_id, flags):
    # Upsert into user_title_flags
    table = db.metadata.tables.get("user_title_flags")
    if not table:
        return False
    stmt = insert(table).values(
        user_id=user_id,
        title_id=title_id,
        has_non_ignored_dlcs=flags.get("has_non_ignored_dlcs", False),
        has_non_ignored_updates=flags.get("has_non_ignored_updates", False),
        has_non_ignored_redundant=flags.get("has_non_ignored_redundant", False),
        updated_at=datetime.datetime.utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "title_id"],
        set_=dict(
            has_non_ignored_dlcs=stmt.excluded.has_non_ignored_dlcs,
            has_non_ignored_updates=stmt.excluded.has_non_ignored_updates,
            has_non_ignored_redundant=stmt.excluded.has_non_ignored_redundant,
            updated_at=stmt.excluded.updated_at,
        ),
    )
    try:
        db.session.execute(stmt)
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False
