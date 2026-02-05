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
    """Obtém lista de wishlist do usuário logado - Otimizado com batch queries"""
    from constants import APP_TYPE_BASE

    # Buscar todos os itens da wishlist
    items = Wishlist.query.filter_by(user_id=current_user.id).order_by(Wishlist.priority.desc()).all()

    if not items:
        return jsonify([])

    # Coletar todos os title_ids
    title_ids = [item.title_id for item in items]

    # BUSCA EM BATCH: Verificar se usuário possui os jogos na biblioteca (1 query única com JOIN)
    owned_entries = db.session.query(Titles.title_id).join(Apps).filter(
        Titles.title_id.in_(title_ids), 
        Apps.app_type == APP_TYPE_BASE, 
        Apps.owned == True
    ).all()

    # Criar mapa para lookup rápido O(1)
    owned_map = {row[0]: True for row in owned_entries}

    result = []
    for item in items:
        # Lookup no mapa (sem query adicional)
        owned = owned_map.get(item.title_id, False)

        # Se o jogo já está na biblioteca, não mostrar na wishlist (nova regra)
        if owned:
            continue

        # Obter informações do título (do cache TitleDB, sem query)
        title_info = titles.get_game_info(item.title_id) or {}

        result.append(
            {
                "id": item.id,
                "title_id": item.title_id,
                "name": title_info.get("name", f"Unknown ({item.title_id})"),
                "iconUrl": title_info.get("iconUrl"),
                "bannerUrl": title_info.get("bannerUrl"),
                "priority": item.priority,
                "added_date": item.added_date.isoformat() if item.added_date else None,
                "owned": False, # Se chegou aqui, owned é obrigatoriamente False
            }
        )

    return jsonify(result)


@wishlist_bp.route("/wishlist", methods=["POST"])
@login_required
def add_to_wishlist():
    """Adiciona jogo à wishlist"""
    data = request.json
    title_id = data.get("title_id")

    if not title_id:
        return jsonify({"success": False, "error": "title_id é obrigatório"}), 400

    existing = Wishlist.query.filter_by(user_id=current_user.id, title_id=title_id).first()
    if existing:
        return jsonify({"success": False, "error": "Jogo já está na wishlist"}), 400

    # Verificar se o jogo já está na biblioteca (usando JOIN com Titles)
    from constants import APP_TYPE_BASE
    owned = Apps.query.join(Titles).filter(
        Titles.title_id == title_id, 
        Apps.app_type == APP_TYPE_BASE, 
        Apps.owned == True
    ).first()
    
    if owned:
        return jsonify({"success": False, "error": "Jogo já está na sua biblioteca"}), 400

    priority = data.get("priority", 0)
    priority = max(0, min(5, priority))

    item = Wishlist(user_id=current_user.id, title_id=title_id, priority=priority)
    db.session.add(item)
    db.session.commit()

    return jsonify({"success": True})


@wishlist_bp.route("/wishlist/<title_id>", methods=["PUT"])
@login_required
def update_wishlist_item(title_id):
    """Atualiza prioridade de um item da wishlist"""
    data = request.json
    priority = data.get("priority", 0)
    priority = max(0, min(5, priority))

    item = Wishlist.query.filter_by(user_id=current_user.id, title_id=title_id).first()
    if not item:
        return jsonify({"success": False, "error": "Item não encontrado"}), 404

    item.priority = priority
    db.session.commit()

    return jsonify({"success": True})


@wishlist_bp.route("/wishlist/<title_id>", methods=["DELETE"])
@login_required
def remove_from_wishlist(title_id):
    """Remove item da wishlist"""
    item = Wishlist.query.filter_by(user_id=current_user.id, title_id=title_id).first()
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
                title_info = titles.get_game_info(item.title_id) or {}
                result.append(
                    {
                        "title_id": item.title_id,
                        "name": title_info.get("name", "Unknown"),
                        "priority": item.priority,
                        "added_date": item.added_date.isoformat() if item.added_date else None,
                    }
                )
            return jsonify(result)

        elif format_type == "csv":
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(["title_id", "name", "priority", "added_date"])
            for item in items:
                title_info = titles.get_game_info(item.title_id) or {}
                writer.writerow(
                    [
                        item.title_id,
                        title_info.get("name", "Unknown"),
                        item.priority,
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
            html += '<table border="1"><tr><th>Title ID</th><th>Name</th><th>Priority</th><th>Added Date</th></tr>'
            for item in items:
                title_info = titles.get_game_info(item.title_id) or {}
                html += f"<tr><td>{item.title_id}</td><td>{title_info.get('name', 'Unknown')}</td>"
                html += f"<td>{item.priority}</td><td>{item.added_date}</td></tr>"
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
