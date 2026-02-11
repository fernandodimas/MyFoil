"""
Web Routes - Rotas principais da aplicação web
"""

from flask import Blueprint, render_template, request, redirect, jsonify, send_from_directory
from flask_login import login_required
from auth import access_required, admin_account_created
from middleware.auth import tinfoil_access
from db import db, Files, Apps, Webhook, logger
import os
import hmac
import hashlib
import requests
from shop import gen_shop_files
from shop import encrypt_shop
from flask import Response
from settings import load_settings
from constants import BUILD_VERSION

web_bp = Blueprint("web", __name__)


@web_bp.route("/")
@web_bp.route("/index.json")
@web_bp.route("/tinfoil.json")
def index():
    """Página inicial / Loja Tinfoil / Índice JSON"""

    @tinfoil_access
    def access_tinfoil_shop():
        shop = {"success": load_settings()["shop"]["motd"]}

        if request.verified_host is not None:
            shop["referrer"] = f"https://{request.verified_host}"

        files_list = gen_shop_files(db)
        shop["files"] = files_list

        if load_settings()["shop"]["encrypt"]:
            return Response(encrypt_shop(shop), mimetype="application/octet-stream")

        return jsonify(shop)

    user_agent = request.headers.get("User-Agent", "")
    is_tinfoil = "Tinfoil" in user_agent or "NintendoSwitch" in user_agent

    # Tinfoil headers check - Relaxed to only require Uid or Hauth as identifiers
    has_tinfoil_headers = any(h in request.headers for h in ["Uid", "Hauth", "Version"])

    # Check if specifically requesting JSON
    is_api_requested = (
        request.path.endswith(".json")
        or request.headers.get("Accept") == "application/json"
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )

    logger.debug(
        f"Request to {request.path} from {request.remote_addr}: UA={user_agent[:50]}..., is_tinfoil={is_tinfoil}, has_tinfoil_headers={has_tinfoil_headers}"
    )

    if is_tinfoil or has_tinfoil_headers or is_api_requested:
        return access_tinfoil_shop()

    # Continue with Web UI logic
    if not load_settings()["shop"]["public"]:
        return access_shop_auth()
    return access_shop()


@web_bp.route("/api/docs")
def api_docs_redirect():
    """Redirecionar para documentação da API"""
    return redirect("/api/docs/")


@web_bp.route("/wishlist")
@login_required
def wishlist_page():
    """Página da wishlist"""
    return render_template("wishlist.html", title="Wishlist", build_version=BUILD_VERSION)


@web_bp.route("/api/get_game/<int:id>")
@tinfoil_access
def serve_game(id):
    """Servir arquivo de jogo para Tinfoil"""
    # TODO add download count increment
    file = Files.query.get(id)
    if not file:
        return "File not found", 404
    filedir, filename = os.path.split(file.filepath)
    return send_from_directory(filedir, filename)


def access_shop():
    """Acesso à página da loja"""
    return render_template(
        "index.html",
        title="Library",
        admin_account_created=admin_account_created(),
        valid_keys=load_settings()["titles"]["valid_keys"],
        total_files=Files.query.count(),
        games=None,
        build_version=BUILD_VERSION,
    )


@access_required("shop")
def access_shop_auth():
    """Acesso autenticado à página da loja"""
    return access_shop()


def tinfoil_error(error):
    """Retornar erro para Tinfoil"""
    return jsonify({"error": error})


def trigger_webhook(event_type, data):
    """Disparar webhooks configurados"""
    # Webhooks removed - placeholder function
    logger.info(f"trigger_webhook called for {event_type} but webhooks feature is removed")


@web_bp.route("/api/renaming/preview", methods=["POST"])
@access_required("admin")
def preview_renaming_api():
    """Pré-visualizar renomeação de arquivos"""
    data = request.json
    patterns = {
        "BASE": data.get("pattern_base"),
        "UPDATE": data.get("pattern_upd"),  # APP_TYPE_UPD constant is 'UPDATE'
        "DLC": data.get("pattern_dlc"),
    }

    from renamer import get_file_metadata, sanitize_filename

    # Get a sample file for each type
    results = []
    types_to_find = ["BASE", "UPDATE", "DLC"]

    for app_type in types_to_find:
        # Find a sample file of this type
        # Join Files -> Apps where app_type matches
        sample_file = db.session.query(Files).join(Files.apps).filter(Apps.app_type == app_type).first()

        if sample_file:
            from renamer import get_file_metadata

            meta = get_file_metadata(sample_file.id)
            if meta:
                pattern = patterns.get(app_type)
                new_name = pattern
                for key, value in meta.items():
                    new_name = new_name.replace(f"{{{key}}}", str(value))
                new_name = sanitize_filename(new_name) + f".{meta['Ext']}"

                results.append({"type": app_type, "original": sample_file.filename, "new": new_name})

    return jsonify({"success": True, "preview": results})


@web_bp.route("/api/renaming/run", methods=["POST"])
@access_required("admin")
def run_renaming_api():
    """Executar renomeação de arquivos"""
    from settings import load_settings
    from renamer import start_renaming_job

    settings = load_settings()
    renaming_cfg = settings.get("renaming", {})

    patterns = {
        "BASE": renaming_cfg.get("pattern_base"),
        "UPDATE": renaming_cfg.get("pattern_upd"),
        "DLC": renaming_cfg.get("pattern_dlc"),
    }

    # Run in background to avoid timeout
    def run_wrapper():
        import app

        with app.app_context():
            start_renaming_job(patterns)

    import threading

    threading.Thread(target=run_wrapper).start()

    return jsonify({"success": True, "message": "Renaming job started in background"})
