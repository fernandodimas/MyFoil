"""
Settings Routes - Endpoints relacionados às configurações do sistema
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user
from db import db, logger
from settings import reload_conf, load_settings, set_titles_settings, set_shop_settings, DEFAULT_SETTINGS, CONFIG_FILE
from auth import access_required
from constants import CONFIG_DIR, TITLEDB_DIR
from utils import format_size_py, format_datetime
from api_responses import success_response, error_response, not_found_response, handle_api_errors, ErrorCode
from repositories.libraries_repository import LibrariesRepository
from repositories.user_repository import UserRepository
from repositories.webhook_repository import WebhookRepository
from repositories.apitoken_repository import ApiTokenRepository
import os
import json
import yaml
import copy

settings_bp = Blueprint("settings", __name__, url_prefix="/api")


@settings_bp.route("/settings")
@access_required("admin")
@handle_api_errors
def get_settings_api():
    """Obter configurações atuais"""
    reload_conf()
    settings = load_settings()

    # Flatten settings for the JS frontend
    flattened = {}
    for section, values in settings.items():
        if isinstance(values, dict):
            for key, value in values.items():
                flattened[f"{section}/{key}"] = value
        else:
            flattened[section] = values

    # Tinfoil Auth specific handling
    if settings.get("shop", {}).get("hauth"):
        flattened["shop/hauth"] = True
    else:
        flattened["shop/hauth"] = False

    return success_response(data=flattened)


@settings_bp.post("/settings/titles")
@access_required("admin")
@handle_api_errors
def set_titles_settings_api():
    """Atualizar configurações de títulos"""
    import logging

    logger = logging.getLogger("main")

    settings = request.json
    logger.info(f"set_titles_settings_api received: {settings}")

    current_settings = load_settings()
    logger.info(f"Current settings: {current_settings.get('titles', {})}")

    region = settings.get("region", current_settings["titles"].get("region", "US"))
    language = settings.get("language", current_settings["titles"].get("language", "en"))
    dbi_versions = settings.get("dbi_versions", current_settings["titles"].get("dbi_versions", False))
    auto_use_latest = settings.get("auto_use_latest")

    logger.info(f"Setting auto_use_latest to: {auto_use_latest}")

    # Only validate region/language if they are being changed
    region_changed = settings.get("region") is not None
    language_changed = settings.get("language") is not None

    if region_changed or language_changed:
        languages_path = os.path.join(TITLEDB_DIR, "languages.json")
        if os.path.exists(languages_path):
            with open(languages_path) as f:
                languages = json.load(f)
                languages = dict(sorted(languages.items()))

            if region not in languages or language not in languages[region]:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    message=f"The region/language pair {region}/{language} is not available.",
                    details=[
                        {"path": "titles", "error": f"The region/language pair {region}/{language} is not available."}
                    ],
                )

    set_titles_settings(region, language, dbi_versions, auto_use_latest)

    logger.info(f"Settings saved: region={region}, language={language}, auto_use_latest={auto_use_latest}")

    reload_conf()

    # Only run TitleDB update if region or language changed
    if region_changed or language_changed:
        from app import update_titledb_job
        import threading

        threading.Thread(target=update_titledb_job, args=(True,)).start()

    return success_response(message="Title settings updated successfully")


@settings_bp.route("/settings/regions")
@access_required("admin")
@handle_api_errors
def get_regions_api():
    """Obter lista de regiões disponíveis"""
    languages_path = os.path.join(TITLEDB_DIR, "languages.json")
    if not os.path.exists(languages_path):
        return success_response(data={"regions": []})

    with open(languages_path) as f:
        languages = json.load(f)
    return success_response(data={"regions": sorted(list(languages.keys()))})


@settings_bp.route("/settings/languages")
@access_required("admin")
@handle_api_errors
def get_languages_api():
    """Obter lista de idiomas disponíveis"""
    languages_path = os.path.join(TITLEDB_DIR, "languages.json")
    if not os.path.exists(languages_path):
        return success_response(data={"languages": []})

    with open(languages_path) as f:
        languages = json.load(f)
    all_langs = set()
    for region_langs in languages.values():
        all_langs.update(region_langs)
    return success_response(data={"languages": sorted(list(all_langs))})


@settings_bp.route("/settings/renaming", methods=["GET", "POST"])
@access_required("admin")
@handle_api_errors
def renaming_settings_api():
    """Gerenciar configurações de renomeação"""
    if request.method == "POST":
        data = request.json
        settings = load_settings()
        if "renaming" not in settings:
            settings["renaming"] = {}

        settings["renaming"]["enabled"] = data.get("enabled", False)
        settings["renaming"]["pattern_base"] = data.get("pattern_base", "{Name} [{TitleID}] [v{Version}]")
        settings["renaming"]["pattern_upd"] = data.get("pattern_upd", "{Name} [UPD] [{TitleID}] [v{Version}]")
        settings["renaming"]["pattern_dlc"] = data.get("pattern_dlc", "{Name} [DLC] [{TitleID}] [v{Version}]")

        with open(CONFIG_FILE, "w") as yaml_file:
            yaml.dump(settings, yaml_file)
        reload_conf()

        return success_response(message="Renaming settings updated")

    settings = load_settings()
    renaming = settings.get("renaming", DEFAULT_SETTINGS["renaming"])
    return success_response(data={"settings": renaming})


@settings_bp.post("/settings/shop")
@handle_api_errors
def set_shop_settings_api():
    """Atualizar configurações da loja"""
    data = request.json
    set_shop_settings(data)
    reload_conf()
    return success_response(message="Shop settings updated")


@settings_bp.route("/settings/library/paths", methods=["GET", "POST", "DELETE"])
@access_required("admin")
@handle_api_errors
def library_paths_api():
    """Gerenciar caminhos da biblioteca"""
    if request.method == "POST":
        data = request.json
        from library import add_library_complete

        success, errors = add_library_complete(current_app, None, data["path"])
        if success:
            reload_conf()
            from library import post_library_change

            post_library_change()
        return (
            success_response(message="Library path added")
            if success
            else error_response(message="Failed to add library path", errors=errors)
        )

    elif request.method == "GET":
        reload_conf()
        stats = LibrariesRepository.get_all_with_stats()
        paths_info = []
        for item in stats:
            l = item["library"]
            paths_info.append(
                {
                    "id": l.id,
                    "path": l.path,
                    "files_count": item["files_count"],
                    "total_size": item["total_size"],
                    "total_size_formatted": format_size_py(item["total_size"]),
                    "titles_count": item["titles_count"],
                    "last_scan": format_datetime(l.last_scan),
                }
            )
        return success_response(data={"paths": paths_info})

    elif request.method == "DELETE":
        data = request.json
        from library import remove_library_complete

        success, errors = remove_library_complete(current_app, None, data["path"])
        if success:
            reload_conf()
            from library import post_library_change

            post_library_change()
        return (
            success_response(message="Library path removed")
            if success
            else error_response(message="Failed to remove library path", errors=errors)
        )


@settings_bp.post("/settings/keys")
@access_required("admin")
@handle_api_errors
def set_keys_api():
    """Atualizar arquivo de chaves"""
    from utils import allowed_file
    from settings import KEYS_FILE

    file = request.files["file"]
    if file and allowed_file(file.filename):
        file.save(KEYS_FILE + ".tmp")
        logger.info(f"Validating {file.filename}...")
        from nstools.nut import Keys

        valid = Keys.load(KEYS_FILE + ".tmp")
        if valid:
            os.rename(KEYS_FILE + ".tmp", KEYS_FILE)
            logger.info("Successfully saved valid keys.txt")
            reload_conf()
            from library import post_library_change

            post_library_change()
            return success_response(message="Keys updated successfully")
        else:
            if os.path.exists(KEYS_FILE + ".tmp"):
                os.remove(KEYS_FILE + ".tmp")
            return error_response(message=f"Invalid keys from {file.filename}")

    return error_response(message="No file or invalid file format")


@settings_bp.route("/settings/titledb/sources", methods=["GET", "POST", "PUT", "DELETE"])
@access_required("admin")
@handle_api_errors
def titledb_sources_api():
    """Gerenciar fontes do TitleDB"""
    import titledb_sources
    from constants import CONFIG_DIR

    manager = titledb_sources.TitleDBSourceManager(CONFIG_DIR)
    if request.method == "GET":
        sources = manager.get_sources_status()
        return success_response(data={"sources": sources})

    elif request.method == "POST":
        data = request.json
        name = data.get("name")
        base_url = data.get("base_url")
        priority = data.get("priority", 50)
        enabled = data.get("enabled", True)
        source_type = data.get("source_type", "json")

        if not name or not base_url:
            return error_response(message="Name and base_url are required")

        success = manager.add_source(name, base_url, priority, enabled, source_type)
        return success_response(message="Source added") if success else error_response(message="Failed to add source")

    elif request.method == "PUT":
        data = request.json
        name = data.get("name")

        if not name:
            return error_response(message="Name is required")

        kwargs = {}
        if "base_url" in data:
            kwargs["base_url"] = data["base_url"]
        if "priority" in data:
            kwargs["priority"] = data["priority"]
        if "enabled" in data:
            kwargs["enabled"] = data["enabled"]
        if "source_type" in data:
            kwargs["source_type"] = data["source_type"]

        success = manager.update_source(name, **kwargs)
        return (
            success_response(message="Source updated") if success else error_response(message="Failed to update source")
        )

    elif request.method == "DELETE":
        data = request.json
        name = data.get("name")

        if not name:
            return error_response(message="Name is required")

        success = manager.remove_source(name)
        return (
            success_response(message="Source removed") if success else error_response(message="Failed to remove source")
        )


@settings_bp.route("/settings/webhooks")
@access_required("admin")
@handle_api_errors
def get_webhooks_api():
    """Webhooks feature removed"""
    # Webhooks removed: return empty list to avoid frontend errors
    return success_response(data=[])


@settings_bp.post("/settings/webhooks")
@access_required("admin")
@handle_api_errors
def add_webhook_api():
    """Webhook management removed"""
    return error_response(ErrorCode.VALIDATION_ERROR, message="Webhooks feature removed", status_code=410)


@settings_bp.delete("/settings/webhooks/<int:id>")
@access_required("admin")
@handle_api_errors
def delete_webhook_api(id):
    """Remover webhook"""
    return error_response(ErrorCode.VALIDATION_ERROR, message="Webhooks feature removed", status_code=410)


@settings_bp.route("/settings/webhooks/<int:id>", methods=["PUT"])
@access_required("admin")
@handle_api_errors
def update_webhook_api(id):
    """Atualizar webhook"""
    return error_response(ErrorCode.VALIDATION_ERROR, message="Webhooks feature removed", status_code=410)


@settings_bp.route("/settings/titledb/sources/reorder", methods=["POST"])
@access_required("admin")
@handle_api_errors
def reorder_sources_api():
    """Reordenar fontes do TitleDB"""
    import logging

    logger = logging.getLogger("main")

    data = request.json
    priorities = data  # Can be dict or list

    import titledb_sources

    manager = titledb_sources.TitleDBSourceManager(CONFIG_DIR)

    updated = 0
    if isinstance(priorities, dict):
        # Frontend sends {source_name: priority, ...}
        for name, priority in priorities.items():
            manager.update_source(name, priority=priority)
            updated += 1
            logger.info(f"Updated source {name} priority to {priority}")
    elif isinstance(priorities, list):
        # Frontend might send [{name, priority}, ...]
        for item in priorities:
            name = item.get("name")
            priority = item.get("priority")
            if name and priority is not None:
                manager.update_source(name, priority=priority)
                updated += 1
                logger.info(f"Updated source {name} priority to {priority}")

    logger.info(f"Reordered {updated} sources")
    return success_response(message=f"Reordered {updated} sources")


@settings_bp.route("/settings/titledb/sources/refresh-dates", methods=["POST"])
@access_required("admin")
@handle_api_errors
def refresh_sources_dates_api():
    """Atualizar datas das fontes do TitleDB"""
    import titledb_sources

    manager = titledb_sources.TitleDBSourceManager(CONFIG_DIR)
    success = manager.refresh_remote_dates()
    return (
        success_response(message="Sources dates refreshed")
        if success
        else error_response(message="Failed to refresh sources dates")
    )


@settings_bp.route("/settings/titledb/refresh_remote", methods=["POST"])
@access_required("admin")
@handle_api_errors
def refresh_titledb_remote_api():
    """
    Manually trigger remote date check for active TitleDB source.
    Used by the UI refresh button in System Status modal.
    """
    import titledb

    # Get active source info (will fetch remote date)
    info = titledb.get_active_source_info(force=True)

    if info:
        return success_response(
            data={"remote_date": info.get("remote_date"), "update_available": info.get("update_available", False)}
        )
    else:
        return error_response(message="No active TitleDB source", code=404)


@settings_bp.route("/users")
@access_required("admin")
@handle_api_errors
def get_users_api():
    """Obter lista de usuários"""
    users = UserRepository.get_all()
    return success_response(
        data=[
            {
                "id": u.id,
                "user": u.user,
                "admin_access": u.admin_access,
                "shop_access": u.shop_access,
                "backup_access": u.backup_access,
            }
            for u in users
        ]
    )


@settings_bp.route("/user", methods=["POST"])
@access_required("admin")
@handle_api_errors
def create_user_api():
    """Criar novo usuário"""
    data = request.json
    username = data.get("user")
    password = data.get("password")
    admin_access = data.get("admin_access", False)
    shop_access = data.get("shop_access", False)
    backup_access = data.get("backup_access", False)

    if not username or not password:
        return error_response(message="Username and password are required")

    from werkzeug.security import generate_password_hash

    hashed_pw = generate_password_hash(password)

    user = UserRepository.create(
        user=username,
        password=hashed_pw,
        admin_access=admin_access,
        shop_access=shop_access,
        backup_access=backup_access,
    )

    return success_response(
        data={
            "user": {
                "id": user.id,
                "user": user.user,
                "admin_access": user.admin_access,
                "shop_access": user.shop_access,
                "backup_access": user.backup_access,
            },
        },
        message="User created",
    )


@settings_bp.route("/user", methods=["DELETE"])
@access_required("admin")
@handle_api_errors
def delete_user_api():
    """Remover usuário"""
    data = request.json
    user_id = data.get("user_id")

    if not user_id:
        return error_response(message="user_id is required")

    if int(user_id) == current_user.id:
        return error_response(message="Cannot delete yourself")

    success = UserRepository.delete(user_id)
    if success:
        return success_response(message="User deleted")
    return not_found_response("User")


@settings_bp.route("/settings/apis", methods=["POST"])
@access_required("admin")
@handle_api_errors
def apis_settings_api():
    """Gerenciar configurações de APIs externas"""
    data = request.json
    settings = load_settings()

    if "apis" not in settings:
        settings["apis"] = {}

    if "rawg_api_key" in data:
        settings["apis"]["rawg_api_key"] = data["rawg_api_key"]

    if "igdb_client_id" in data:
        settings["apis"]["igdb_client_id"] = data["igdb_client_id"]

    if "igdb_client_secret" in data:
        settings["apis"]["igdb_client_secret"] = data["igdb_client_secret"]

    if "upcoming_days_ahead" in data:
        settings["apis"]["upcoming_days_ahead"] = int(data["upcoming_days_ahead"])

    with open(CONFIG_FILE, "w") as yaml_file:
        import yaml

        yaml.dump(settings, yaml_file)

    reload_conf()
    return success_response(message="API settings updated")


@settings_bp.route("/settings/tokens", methods=["GET"])
@access_required("admin")
@handle_api_errors
def get_tokens_api():
    """Get all API tokens"""
    tokens = ApiTokenRepository.get_all()
    return success_response(
        data=[
            {
                "id": t.id,
                "name": t.name,
                "user_id": t.user_id,
                "user_name": t.user.user if t.user else "Unknown",
                "created_at": format_datetime(t.created_at),
                "last_used": format_datetime(t.last_used),
                "prefix": t.token[:8] + "...",
            }
            for t in tokens
        ]
    )


@settings_bp.route("/settings/tokens", methods=["POST"])
@access_required("admin")
@handle_api_errors
def create_token_api():
    """Create a new API token"""
    import secrets

    data = request.json
    name = data.get("name")

    # Determine target user_id for the token. Prefer explicit payload, then
    # the logged-in session user, then a valid bearer token's user.
    user_id = data.get("user_id") if data else None
    if not user_id:
        try:
            if current_user and getattr(current_user, "is_authenticated", False):
                user_id = current_user.id
        except Exception:
            user_id = None

    # If still no user_id, attempt to extract from Authorization Bearer token
    if not user_id:
        try:
            from auth import check_api_token

            token_valid, _, user_obj = check_api_token(request)
            if token_valid and user_obj:
                user_id = user_obj.id
        except Exception:
            # ignore and let validation below catch missing user
            pass

    if not name:
        return error_response(message="Name is required")

    token_str = secrets.token_hex(32)

    new_token = ApiTokenRepository.create(user_id=user_id, name=name, token=token_str)

    return success_response(
        data={"token": token_str, "id": new_token.id, "name": new_token.name}, message="Token created"
    )


@settings_bp.route("/settings/tokens/<int:id>", methods=["DELETE"])
@access_required("admin")
@handle_api_errors
def delete_token_api(id):
    """Revoke an API token"""
    success = ApiTokenRepository.delete(id)
    if success:
        return success_response(message="Token revoked")
    return not_found_response("Token")
