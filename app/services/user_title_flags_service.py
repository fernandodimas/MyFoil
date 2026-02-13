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


def compute_flags_for_user_title(user_id, title_id, title_apps):
    # title_apps: list of app dicts as used elsewhere
    ignores = get_flattened_ignores_for_user(user_id).get(title_id, {})
    ignored_dlcs = set(k.upper() for k in ignores.get("dlcs", []))
    ignored_updates = set(str(k) for k in ignores.get("updates", []))

    # compute possible dlcs from TitleDB (cheap cached calls)
    try:
        dlcs = titles_lib.get_all_existing_dlc(title_id) or []
    except Exception:
        dlcs = []

    owned_dlc_ids = set(
        [a.get("app_id", "").upper() for a in title_apps if a.get("app_type") == "dlc" and a.get("owned")]
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

    owned_versions = set(
        int(a.get("app_version") or 0) for a in title_apps if a.get("app_type") == "upd" and a.get("owned")
    )
    current_owned_version = max(owned_versions) if owned_versions else 0

    has_non_ignored_updates = False
    for vinfo in versions:
        v = int(vinfo.get("version") or 0)
        if v <= current_owned_version:
            continue
        if str(v) not in ignored_updates:
            has_non_ignored_updates = True
            break

    # redundant - reuse updates logic as conservative check
    has_non_ignored_redundant = has_non_ignored_updates

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
