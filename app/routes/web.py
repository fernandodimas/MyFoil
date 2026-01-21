"""
Web Routes - Rotas principais da aplicação web
"""

from flask import Blueprint, render_template, request, redirect, jsonify, send_from_directory
from flask_login import login_required
from auth import access_required, admin_account_created
from middleware.auth import tinfoil_access
from db import *
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
def index():
    """Página inicial / Loja Tinfoil"""

    @tinfoil_access
    def access_tinfoil_shop():
        shop = {"success": load_settings()["shop"]["motd"]}

        if request.verified_host is not None:
            shop["referrer"] = f"https://{request.verified_host}"

        files_list, titles_map = gen_shop_files(db)
        shop["files"] = files_list
        shop["titles"] = titles_map

        if load_settings()["shop"]["encrypt"]:
            return Response(encrypt_shop(shop), mimetype="application/octet-stream")

        return jsonify(shop)

    user_agent = request.headers.get("User-Agent", "")
    is_tinfoil = "Tinfoil" in user_agent or "NintendoSwitch" in user_agent

    # Tinfoil requests typically don't have Accept header or have specific patterns
    is_api_request = (
        request.headers.get("Accept") == "application/json"
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or is_tinfoil
    )

    logger.info(
        f"Request from {request.remote_addr}: UA={user_agent[:50]}..., is_tinfoil={is_tinfoil}, is_api={is_api_request}"
    )

    if is_tinfoil or is_api_request:
        return access_tinfoil_shop()

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
    with app.app_context():
        try:
            webhooks = Webhook.query.filter_by(active=True).all()
            for webhook in webhooks:
                # Check if this webhook is interested in this event
                import json

                events = json.loads(webhook.events) if webhook.events else []
                if event_type not in events:
                    continue

                payload = {"event": event_type, "timestamp": datetime.datetime.now().isoformat(), "data": data}

                headers = {"Content-Type": "application/json"}
                if webhook.secret:
                    signature = hmac.new(
                        webhook.secret.encode(), json.dumps(payload).encode(), hashlib.sha256
                    ).hexdigest()
                    headers["X-MyFoil-Signature"] = signature

                try:
                    requests.post(webhook.url, json=payload, headers=headers, timeout=5)
                    logger.debug(f"Webhook {webhook.url} triggered for {event_type}")
                except Exception as e:
                    logger.warning(f"Failed to trigger webhook {webhook.url}: {e}")
        except Exception as e:
            logger.error(f"Error in trigger_webhook: {e}")


@web_bp.route("/api/renaming/preview")
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


@web_bp.route("/api/renaming/run")
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
        with app.app_context():
            start_renaming_job(patterns)

    import threading

    threading.Thread(target=run_wrapper).start()

    return jsonify({"success": True, "message": "Renaming job started in background"})
