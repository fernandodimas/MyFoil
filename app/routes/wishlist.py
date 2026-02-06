"""
Wishlist Routes - Endpoints para gerenciar lista de desejos
"""

from flask import Blueprint, jsonify, request, Response
from flask_login import current_user, login_required
from db import db, Apps, Titles, Wishlist, WishlistIgnore
import titles
import csv
from io import StringIO

wishlist_bp = Blueprint("wishlist", __name__, url_prefix="/api")


@wishlist_bp.route("/wishlist")
@login_required
def get_wishlist():
    """Obtém lista de wishlist do usuário logado - Agora independente do TitleDB"""
    from constants import APP_TYPE_BASE

    # Buscar todos os itens da wishlist (ordenados por data de adição)
    items = Wishlist.query.filter_by(user_id=current_user.id).order_by(Wishlist.added_date.desc()).all()

    if not items:
        return jsonify([])

    # Coletar todos os title_ids para verificar se já possui na biblioteca
    title_ids = [item.title_id for item in items if item.title_id]

    # Verificar se usuário possui os jogos na biblioteca
    owned_map = {}
    if title_ids:
        owned_entries = db.session.query(Titles.title_id).join(Apps).filter(
            Titles.title_id.in_(title_ids), 
            Apps.app_type == APP_TYPE_BASE, 
            Apps.owned == True
        ).all()
        owned_map = {row[0]: True for row in owned_entries}

    result = []
    for item in items:
        # Se o jogo já está na biblioteca, não mostrar na wishlist
        if item.title_id and owned_map.get(item.title_id):
            continue

        result.append(
            {
                "id": item.id,
                "title_id": item.title_id,
                "name": item.name or f"Unknown ({item.title_id})",
                "iconUrl": item.icon_url or "/static/img/no-icon.png",
                "bannerUrl": item.banner_url,
                "release_date": item.release_date,
                "added_date": item.added_date.isoformat() if item.added_date else None,
                "owned": False,
            }
        )

    return jsonify(result)


@wishlist_bp.route("/wishlist", methods=["POST"])
@login_required
def add_to_wishlist():
    """Adiciona jogo à wishlist"""
    data = request.json
    name = data.get("name")
    title_id = data.get("title_id")

    if not name and not title_id:
        return jsonify({"success": False, "error": "Nome ou title_id é obrigatório"}), 400

    # Evitar duplicatas por title_id se presente
    if title_id:
        existing = Wishlist.query.filter_by(user_id=current_user.id, title_id=title_id).first()
        if existing:
            return jsonify({"success": False, "error": "Jogo já está na wishlist"}), 400

        # Verificar se está na biblioteca
        from constants import APP_TYPE_BASE
        owned = Apps.query.join(Titles).filter(
            Titles.title_id == title_id, 
            Apps.app_type == APP_TYPE_BASE, 
            Apps.owned == True
        ).first()
        if owned:
            return jsonify({"success": False, "error": "Jogo já está na sua biblioteca"}), 400
    elif name:
        # Evitar duplicatas por nome se não tiver title_id
        existing = Wishlist.query.filter_by(user_id=current_user.id, name=name).first()
        if existing:
            return jsonify({"success": False, "error": "Jogo já está na wishlist"}), 400

    display_name = name
    release_date = data.get("release_date")
    icon_url = data.get("icon_url")
    banner_url = data.get("banner_url")

    # Fetch metadata if using title_id
    if title_id and (not display_name or not release_date):
        game_info = titles.get_game_info(title_id)
        if game_info:
            if not display_name:
                display_name = game_info.get("name")
            if not release_date:
                release_date = game_info.get("releaseDate") or game_info.get("release_date")
            if not icon_url:
                icon_url = game_info.get("iconUrl")
            if not banner_url:
                banner_url = game_info.get("bannerUrl")

    item = Wishlist(
        user_id=current_user.id, 
        title_id=title_id, 
        name=display_name,
        release_date=release_date,
        icon_url=icon_url,
        banner_url=banner_url
    )
    db.session.add(item)
    db.session.commit()

    return jsonify({"success": True})


@wishlist_bp.route("/wishlist/<title_id>", methods=["PUT"])
@login_required
def update_wishlist_item(title_id):
    """Atualiza um item da wishlist (Priority removida)"""
    return jsonify({"success": True})


@wishlist_bp.route("/wishlist/<int:item_id>", methods=["DELETE"])
@login_required
def remove_from_wishlist(item_id):
    """Remove item da wishlist pelo ID do banco"""
    item = Wishlist.query.filter_by(user_id=current_user.id, id=item_id).first()
    if not item:
        return jsonify({"success": False, "error": "Item não encontrado"}), 404

    db.session.delete(item)
    db.session.commit()

    return jsonify({"success": True})


@wishlist_bp.route("/wishlist/export")
@login_required
def export_wishlist():
    """Exporta wishlist em json, csv ou html"""
    try:
        format_type = request.args.get("format", "json")

        items = Wishlist.query.filter_by(user_id=current_user.id).order_by(Wishlist.priority.desc()).all()

        if format_type == "json":
            result = []
            for item in items:
                result.append(
                    {
                        "title_id": item.title_id,
                        "name": item.name or "Unknown",
                        "added_date": item.added_date.isoformat() if item.added_date else None,
                    }
                )
            return jsonify(result)

        elif format_type == "csv":
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(["title_id", "name", "added_date"])
            for item in items:
                writer.writerow(
                    [
                        item.title_id or "",
                        item.name or "Unknown",
                        item.added_date.isoformat() if item.added_date else "",
                    ]
                )
            return Response(
                output.getvalue(),
                mimetype="text/csv",
                headers={"Content-Disposition": "attachment; filename=wishlist.csv"},
            )

        elif format_type == "html":
            html = "<html><head><title>Wishlist Export</title></head><body>"
            html += "<h1>Wishlist</h1>"
            html += '<table border="1"><tr><th>Name</th><th>Added Date</th></tr>'
            for item in items:
                html += f"<tr><td>{item.name or 'Unknown'}</td>"
                html += f"<td>{item.added_date}</td></tr>"
            html += "</table></body></html>"
            return Response(html, mimetype="text/html")

        return jsonify({"error": "Formato não suportado. Use json, csv ou html"}), 400
    except Exception as e:
        import logging

        logger = logging.getLogger("main")
        logger.error(f"Error exporting wishlist: {e}")
        return jsonify({"error": str(e)}), 500


@wishlist_bp.route("/wishlist/ignore/<title_id>", methods=["POST"])
@login_required
def set_wishlist_ignore(title_id):
    """Define preferências de ignore para um item da wishlist"""
    import json

    data = request.json or {}

    item_type = data.get("type")  # 'dlc' or 'update'
    item_id = data.get("item_id")
    ignored = data.get("ignored", False)

    if not item_type or not item_id:
        return jsonify({"success": False, "error": "type and item_id are required"}), 400

    ignore_record = WishlistIgnore.query.filter_by(user_id=current_user.id, title_id=title_id).first()

    if not ignore_record:
        ignore_record = WishlistIgnore(
            user_id=current_user.id, title_id=title_id, ignore_dlcs="{}", ignore_updates="{}"
        )
        db.session.add(ignore_record)
        db.session.flush()

    if item_type == "dlc":
        dlcs = json.loads(ignore_record.ignore_dlcs) if ignore_record.ignore_dlcs else {}
        dlcs[item_id] = ignored
        ignore_record.ignore_dlcs = json.dumps(dlcs)
    else:
        updates = json.loads(ignore_record.ignore_updates) if ignore_record.ignore_updates else {}
        updates[item_id] = ignored
        ignore_record.ignore_updates = json.dumps(updates)

    db.session.commit()

    return jsonify({"success": True})


@wishlist_bp.route("/wishlist/ignore/<title_id>")
@login_required
def get_wishlist_ignore(title_id):
    """Obtém preferências de ignore para um item da wishlist"""
    import json

    ignore_record = WishlistIgnore.query.filter_by(user_id=current_user.id, title_id=title_id).first()

    if ignore_record:
        dlcs = json.loads(ignore_record.ignore_dlcs) if ignore_record.ignore_dlcs else {}
        updates = json.loads(ignore_record.ignore_updates) if ignore_record.ignore_updates else {}
    else:
        dlcs = {}
        updates = {}

    return jsonify({"success": True, "dlcs": dlcs, "updates": updates})


@wishlist_bp.route("/wishlist/ignore")
@login_required
def get_all_wishlist_ignore():
    """Obtém todas as preferências de ignore do usuário"""
    import json

    ignore_records = WishlistIgnore.query.filter_by(user_id=current_user.id).all()

    result = {}
    for record in ignore_records:
        result[record.title_id] = {
            "dlcs": json.loads(record.ignore_dlcs) if record.ignore_dlcs else {},
            "updates": json.loads(record.ignore_updates) if record.ignore_updates else {},
        }

    return jsonify(result)
