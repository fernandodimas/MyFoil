"""
Settings Routes - Endpoints relacionados às configurações do sistema
"""

from flask import Blueprint, request, jsonify
from flask_login import current_user
from db import *
from db import app_files
from sqlalchemy import func
from settings import reload_conf, load_settings, set_titles_settings, set_shop_settings, DEFAULT_SETTINGS, CONFIG_FILE
from auth import access_required
from constants import CONFIG_DIR
from utils import format_size_py
import os
import json
import copy

settings_bp = Blueprint("settings", __name__, url_prefix="/api")


@settings_bp.route("/settings")
@access_required("admin")
def get_settings_api():
    """Obter configurações atuais"""
    try:
        reload_conf()
        import app

        settings = copy.deepcopy(app.app_settings)

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

        return jsonify(flattened)
    except Exception as e:
        import logging

        logger = logging.getLogger("main")
        logger.error(f"Error in get_settings_api: {e}")
        return jsonify({"error": str(e)}), 500


@settings_bp.post("/settings/titles")
@access_required("admin")
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
                resp = {
                    "success": False,
                    "errors": [
                        {"path": "titles", "error": f"The region/language pair {region}/{language} is not available."}
                    ],
                }
                return jsonify(resp)

    set_titles_settings(region, language, dbi_versions, auto_use_latest)
    logger.info(f"Settings saved: region={region}, language={language}, auto_use_latest={auto_use_latest}")

    reload_conf()

    # Only run TitleDB update if region or language changed
    if region_changed or language_changed:
        from app import update_titledb_job
        import threading

        threading.Thread(target=update_titledb_job, args=(True,)).start()

    resp = {"success": True, "errors": []}
    return jsonify(resp)


@settings_bp.route("/settings/regions")
@access_required("admin")
def get_regions_api():
    """Obter lista de regiões disponíveis"""
    languages_path = os.path.join(TITLEDB_DIR, "languages.json")
    if not os.path.exists(languages_path):
        return jsonify({"regions": []})
    try:
        with open(languages_path) as f:
            languages = json.load(f)
        return jsonify({"regions": sorted(list(languages.keys()))})
    except:
        return jsonify({"regions": []})


@settings_bp.route("/settings/languages")
@access_required("admin")
def get_languages_api():
    """Obter lista de idiomas disponíveis"""
    languages_path = os.path.join(TITLEDB_DIR, "languages.json")
    if not os.path.exists(languages_path):
        return jsonify({"languages": []})
    try:
        with open(languages_path) as f:
            languages = json.load(f)
        all_langs = set()
        for region_langs in languages.values():
            all_langs.update(region_langs)
        return jsonify({"languages": sorted(list(all_langs))})
    except:
        return jsonify({"languages": []})


@settings_bp.route("/settings/renaming", methods=["GET", "POST"])
@access_required("admin")
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

        return jsonify({"success": True})

    settings = load_settings()
    renaming = settings.get("renaming", DEFAULT_SETTINGS["renaming"])
    return jsonify({"success": True, "settings": renaming})


@settings_bp.post("/settings/shop")
def set_shop_settings_api():
    """Atualizar configurações da loja"""
    data = request.json
    set_shop_settings(data)
    reload_conf()
    resp = {"success": True, "errors": []}
    return jsonify(resp)


@settings_bp.route("/settings/library/paths", methods=["GET", "POST", "DELETE"])
@access_required("admin")
def library_paths_api():
    """Gerenciar caminhos da biblioteca"""
    try:
        if request.method == "POST":
            data = request.json
            import app
            from library import add_library_complete

            success, errors = add_library_complete(app.app, app.watcher, data["path"])
            if success:
                reload_conf()
                from library import post_library_change

                post_library_change()
            resp = {"success": success, "errors": errors}
        elif request.method == "GET":
            reload_conf()
            libs = Libraries.query.all()
            paths_info = []
            for l in libs:
                files_count = Files.query.filter_by(library_id=l.id).count()
                total_size = db.session.query(func.sum(Files.size)).filter_by(library_id=l.id).scalar() or 0

                try:
                    # Use subquery to avoid select_from conflict
                    subquery = (
                        db.session.query(Apps.title_id)
                        .distinct()
                        .join(app_files, Apps.id == app_files.c.app_id)
                        .join(Files, Files.id == app_files.c.file_id)
                        .filter(Files.library_id == l.id)
                    )
                    titles_count = subquery.count()
                except Exception as e:
                    logger.error(f"Error counting titles for path {l.path}: {e}")
                    titles_count = 0

                paths_info.append(
                    {
                        "id": l.id,
                        "path": l.path,
                        "files_count": files_count,
                        "total_size": total_size,
                        "total_size_formatted": format_size_py(total_size),
                        "titles_count": titles_count,
                        "last_scan": l.last_scan.strftime("%Y-%m-%d %H:%M:%S") if l.last_scan else "Nunca",
                    }
                )

            resp = {"success": True, "errors": [], "paths": paths_info}
        elif request.method == "DELETE":
            data = request.json
            import app
            from library import remove_library_complete

            success, errors = remove_library_complete(app.app, app.watcher, data["path"])
            if success:
                reload_conf()
                from library import post_library_change

                post_library_change()
            resp = {"success": success, "errors": errors}
        return jsonify(resp)
    except Exception as e:
        logger.error(f"Error in library_paths_api: {e}")
        return jsonify({"success": False, "errors": [str(e)]}), 500


@settings_bp.post("/settings/keys")
@access_required("admin")
def set_keys_api():
    """Atualizar arquivo de chaves"""
    from utils import allowed_file
    from settings import KEYS_FILE

    errors = []
    success = False

    file = request.files["file"]
    if file and allowed_file(file.filename):
        # filename = secure_filename(file.filename)
        file.save(KEYS_FILE + ".tmp")
        logger.info(f"Validating {file.filename}...")
        from nstools.nut import Keys

        valid = Keys.load(KEYS_FILE + ".tmp")
        if valid:
            os.rename(KEYS_FILE + ".tmp", KEYS_FILE)
            success = True
            logger.info("Successfully saved valid keys.txt")
            reload_conf()
            from library import post_library_change

            post_library_change()
        else:
            os.remove(KEYS_FILE + ".tmp")
            logger.error(f"Invalid keys from {file.filename}")

    resp = {"success": success, "errors": errors}
    return jsonify(resp)


@settings_bp.route("/settings/titledb/sources", methods=["GET", "POST", "PUT", "DELETE"])
@access_required("admin")
def titledb_sources_api():
    """Gerenciar fontes do TitleDB"""
    try:
        import titledb_sources
        from constants import CONFIG_DIR

        manager = titledb_sources.TitleDBSourceManager(CONFIG_DIR)
        if request.method == "GET":
            sources = manager.get_sources_status()
            return jsonify({"success": True, "sources": sources})

        elif request.method == "POST":
            data = request.json
            name = data.get("name")
            base_url = data.get("base_url")
            priority = data.get("priority", 50)
            enabled = data.get("enabled", True)
            source_type = data.get("source_type", "json")

            if not name or not base_url:
                return jsonify({"success": False, "errors": ["Name and base_url are required"]})

            manager = titledb_sources.TitleDBSourceManager(CONFIG_DIR)
            success = manager.add_source(name, base_url, priority, enabled, source_type)
            return jsonify({"success": success, "errors": [] if success else ["Failed to add source"]})

        elif request.method == "PUT":
            data = request.json
            name = data.get("name")

            if not name:
                return jsonify({"success": False, "errors": ["Name is required"]})

            kwargs = {}
            if "base_url" in data:
                kwargs["base_url"] = data["base_url"]
            if "priority" in data:
                kwargs["priority"] = data["priority"]
            if "enabled" in data:
                kwargs["enabled"] = data["enabled"]
            if "source_type" in data:
                kwargs["source_type"] = data["source_type"]

            manager = titledb_sources.TitleDBSourceManager(CONFIG_DIR)
            success = manager.update_source(name, **kwargs)
            return jsonify({"success": success, "errors": [] if success else ["Failed to update source"]})

        elif request.method == "DELETE":
            data = request.json
            name = data.get("name")

            if not name:
                return jsonify({"success": False, "errors": ["Name is required"]})

            manager = titledb_sources.TitleDBSourceManager(CONFIG_DIR)
            success = manager.remove_source(name)
            return jsonify({"success": success, "errors": [] if success else ["Failed to remove source"]})
    except Exception as e:
        logger.error(f"Error in titledb_sources_api: {e}")
        return jsonify({"success": False, "errors": [str(e)]}), 500


@settings_bp.route("/settings/webhooks")
@access_required("admin")
def get_webhooks_api():
    """Obter webhooks configurados"""
    webhooks = Webhook.query.all()
    return jsonify([w.to_dict() for w in webhooks])


@settings_bp.post("/settings/webhooks")
@access_required("admin")
def add_webhook_api():
    """Adicionar webhook"""
    data = request.json
    import json

    webhook = Webhook(
        url=data["url"],
        events=json.dumps(data.get("events", ["library_updated"])),
        secret=data.get("secret"),
        active=data.get("active", True),
    )
    db.session.add(webhook)
    try:
        db.session.commit()
        from app import log_activity

        log_activity("webhook_created", details={"url": webhook.url}, user_id=current_user.id)
        return jsonify({"success": True, "webhook": webhook.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@settings_bp.delete("/settings/webhooks/<int:id>")
@access_required("admin")
def delete_webhook_api(id):
    """Remover webhook"""
    webhook = db.session.get(Webhook, id)
    if webhook:
        db.session.delete(webhook)
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Webhook not found"}), 404


@settings_bp.route("/settings/webhooks/<int:id>", methods=["PUT"])
@access_required("admin")
def update_webhook_api(id):
    """Atualizar webhook"""
    data = request.json
    webhook = db.session.get(Webhook, id)
    if not webhook:
        return jsonify({"success": False, "error": "Webhook not found"}), 404

    if "url" in data:
        webhook.url = data["url"]
    if "events" in data:
        import json

        webhook.events = json.dumps(data["events"])
    if "secret" in data:
        webhook.secret = data["secret"]
    if "active" in data:
        webhook.active = data["active"]

    try:
        db.session.commit()
        return jsonify({"success": True, "webhook": webhook.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@settings_bp.route("/settings/titledb/sources/reorder", methods=["POST"])
@access_required("admin")
def reorder_sources_api():
    """Reordenar fontes do TitleDB"""
    data = request.json
    priorities = data.get("priorities", [])

    import titledb_sources

    manager = titledb_sources.TitleDBSourceManager(CONFIG_DIR)

    for item in priorities:
        name = item.get("name")
        priority = item.get("priority")
        if name and priority is not None:
            manager.update_source(name, priority=priority)

    return jsonify({"success": True})


@settings_bp.route("/settings/titledb/sources/refresh-dates", methods=["POST"])
@access_required("admin")
def refresh_sources_dates_api():
    """Atualizar datas das fontes do TitleDB"""
    import titledb_sources

    manager = titledb_sources.TitleDBSourceManager(CONFIG_DIR)
    success = manager.refresh_remote_dates()
    return jsonify({"success": success})


@settings_bp.route("/users")
@access_required("admin")
def get_users_api():
    """Obter lista de usuários"""
    users = User.query.all()
    return jsonify(
        [
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
def create_user_api():
    """Criar novo usuário"""
    data = request.json
    username = data.get("user")
    password = data.get("password")
    admin_access = data.get("admin_access", False)
    shop_access = data.get("shop_access", False)
    backup_access = data.get("backup_access", False)

    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400

    from werkzeug.security import generate_password_hash

    hashed_pw = generate_password_hash(password)

    user = User(
        user=username,
        password=hashed_pw,
        admin_access=admin_access,
        shop_access=shop_access,
        backup_access=backup_access,
    )

    try:
        db.session.add(user)
        db.session.commit()
        return jsonify(
            {
                "success": True,
                "user": {
                    "id": user.id,
                    "user": user.user,
                    "admin_access": user.admin_access,
                    "shop_access": user.shop_access,
                    "backup_access": user.backup_access,
                },
            }
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@settings_bp.route("/user", methods=["DELETE"])
@access_required("admin")
def delete_user_api():
    """Remover usuário"""
    data = request.json
    user_id = data.get("user_id")

    if not user_id:
        return jsonify({"success": False, "error": "user_id is required"}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    if user.id == current_user.id:
        return jsonify({"success": False, "error": "Cannot delete yourself"}), 400

    try:
        db.session.delete(user)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400
