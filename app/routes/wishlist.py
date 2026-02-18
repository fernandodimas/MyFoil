"""
Wishlist Routes - Endpoints para gerenciar lista de desejos
Phase 3.1: Standardized API & Repository Pattern
"""

import csv
import json
from io import StringIO
from flask import Blueprint, request, Response
from flask_login import current_user, login_required
import titles
from api_responses import (
    success_response,
    error_response,
    handle_api_errors,
    ErrorCode,
    not_found_response,
)
from repositories.wishlist_repository import WishlistRepository
from repositories.titles_repository import TitlesRepository
from repositories.wishlistignore_repository import WishlistIgnoreRepository

wishlist_bp = Blueprint("wishlist", __name__, url_prefix="/api")


@wishlist_bp.route("/wishlist")
@login_required
@handle_api_errors
def get_wishlist():
    """Obtém lista de wishlist do usuário logado"""
    # Buscar todos os itens da wishlist (ordenados por data de adição)
    items = WishlistRepository.get_all_by_user(current_user.id)

    if not items:
        return success_response(data=[])

    # Coletar todos os title_ids para verificar se já possui na biblioteca
    title_ids = [item.title_id for item in items if item.title_id]

    # Verificar se usuário possui os jogos na biblioteca
    owned_ids = TitlesRepository.get_owned_ids_from_list(title_ids) if title_ids else []
    owned_map = {tid: True for tid in owned_ids}

    result = []
    for item in items:
        # Se o jogo já está na biblioteca, não mostrar na wishlist
        if item.title_id and owned_map.get(item.title_id):
            continue

        # Self-healing: Check if metadata is missing and try to fetch it
        if item.title_id and (not item.release_date or not item.icon_url or not item.banner_url):
            game_info = titles.get_game_info(item.title_id)
            if game_info:
                updated_data = {}
                if not item.release_date and (game_info.get("releaseDate") or game_info.get("release_date")):
                    updated_data["release_date"] = game_info.get("releaseDate") or game_info.get("release_date")

                if not item.icon_url and game_info.get("iconUrl"):
                    updated_data["icon_url"] = game_info.get("iconUrl")

                if not item.banner_url and game_info.get("bannerUrl"):
                    updated_data["banner_url"] = game_info.get("bannerUrl")

                if not item.name or item.name.startswith("Unknown"):
                    if game_info.get("name"):
                        updated_data["name"] = game_info.get("name")

                if updated_data:
                    WishlistRepository.update(item.id, **updated_data)

        result.append(
            {
                "id": item.id,
                "title_id": item.title_id,
                "name": item.name or f"Unknown ({item.title_id})",
                "iconUrl": item.icon_url or "/static/img/no-icon.png",
                "bannerUrl": item.banner_url,
                "release_date": item.release_date,
                "description": item.description,
                "genres": item.genres,
                "screenshots": item.screenshots,
                "added_date": item.added_date.isoformat() if item.added_date else None,
                "owned": False,
            }
        )

    return success_response(data=result)


@wishlist_bp.route("/wishlist", methods=["POST"])
@login_required
@handle_api_errors
def add_to_wishlist():
    """Adiciona jogo à wishlist"""
    data = request.json
    name = data.get("name")
    title_id = data.get("title_id")

    if not name and not title_id:
        return error_response(ErrorCode.INVALID_PARAMS, "Nome ou title_id é obrigatório")

    # Evitar duplicatas por title_id se presente
    if title_id:
        existing = WishlistRepository.get_by_user_and_title(current_user.id, title_id)
        if existing:
            return error_response(ErrorCode.CONFLICT, "Jogo já está na wishlist")

        # Verificar se está na biblioteca
        owned_ids = TitlesRepository.get_owned_ids_from_list([title_id])
        if owned_ids:
            return error_response(ErrorCode.CONFLICT, "Jogo já está na sua biblioteca")
    elif name:
        # Evitar duplicatas por nome se não tiver title_id
        items = WishlistRepository.get_all_by_user(current_user.id)
        if any(item.name == name for item in items):
            return error_response(ErrorCode.CONFLICT, "Jogo já está na wishlist")

    display_name = name
    release_date = data.get("release_date")
    icon_url = data.get("icon_url")
    banner_url = data.get("banner_url")
    description = data.get("description")
    genres = data.get("genres")
    screenshots = data.get("screenshots")

    # Fetch metadata if using title_id
    if title_id and (not display_name or not release_date):
        game_info = titles.get_game_info(title_id)
        if game_info:
            display_name = display_name or game_info.get("name")
            release_date = release_date or game_info.get("releaseDate") or game_info.get("release_date")
            icon_url = icon_url or game_info.get("iconUrl")
            banner_url = banner_url or game_info.get("bannerUrl")
            description = description or game_info.get("description")
            if not genres:
                g = game_info.get("category")
                genres = ",".join(g) if isinstance(g, list) else g

    WishlistRepository.create(
        user_id=current_user.id,
        title_id=title_id,
        name=display_name,
        release_date=release_date,
        icon_url=icon_url,
        banner_url=banner_url,
        description=description,
        genres=genres,
        screenshots=screenshots,
    )

    return success_response(message="Jogo adicionado à wishlist")


@wishlist_bp.route("/wishlist/<title_id>", methods=["PUT"])
@login_required
@handle_api_errors
def update_wishlist_item(title_id):
    """Atualiza um item da wishlist (Priority removida)"""
    return success_response(message="Item atualizado")


@wishlist_bp.route("/wishlist/<identifier>", methods=["DELETE"])
@login_required
@handle_api_errors
def remove_from_wishlist(identifier):
    """Remove item da wishlist pelo ID do banco (int) ou title_id (string)"""
    item = None
    if identifier.isdigit():
        item = WishlistRepository.get_by_user_and_id(current_user.id, int(identifier))

    if not item:
        item = WishlistRepository.get_by_user_and_title(current_user.id, identifier)

    if not item:
        return not_found_response("Wishlist item")

    WishlistRepository.delete(item.id)
    return success_response(message="Item removido da wishlist", data={"id": item.id})


@wishlist_bp.route("/wishlist/debug", methods=["GET"])
@login_required
@handle_api_errors
def debug_wishlist():
    """Debug endpoint to check wishlist data"""
    items = WishlistRepository.get_all_by_user(current_user.id)

    debug_data = {
        "user_id": current_user.id,
        "user_authenticated": current_user.is_authenticated,
        "items_count": len(items),
        "items": [
            {
                "id": item.id,
                "title_id": item.title_id,
                "name": item.name,
                "added_date": item.added_date.isoformat() if item.added_date else None,
            }
            for item in items
        ],
    }
    return success_response(data=debug_data)


@wishlist_bp.route("/wishlist/export")
@login_required
@handle_api_errors
def export_wishlist():
    """Exporta wishlist em json, csv ou html"""
    format_type = request.args.get("format", "json")
    items = WishlistRepository.get_all_by_user(current_user.id)

    if format_type == "json":
        result = [
            {
                "title_id": item.title_id,
                "name": item.name or "Unknown",
                "added_date": item.added_date.isoformat() if item.added_date else None,
            }
            for item in items
        ]
        return success_response(data=result)

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

    return error_response(ErrorCode.INVALID_PARAMS, "Formato não suportado. Use json, csv ou html")


@wishlist_bp.route("/wishlist/ignore/<title_id>", methods=["POST"])
@login_required
@handle_api_errors
def set_wishlist_ignore(title_id):
    """Define preferências de ignore para um item da wishlist"""
    data = request.json or {}
    item_type = data.get("type")  # 'dlc' or 'update'
    item_id = data.get("item_id")
    ignored = data.get("ignored", False)

    if not item_type or not item_id:
        return error_response(ErrorCode.INVALID_PARAMS, "type and item_id are required")

    ignore_record = WishlistIgnoreRepository.get_by_user_and_title(current_user.id, title_id)

    if not ignore_record:
        ignore_record = WishlistIgnoreRepository.create(
            user_id=current_user.id, title_id=title_id, ignore_dlcs="{}", ignore_updates="{}"
        )

    if item_type == "dlc":
        dlcs = json.loads(ignore_record.ignore_dlcs) if ignore_record.ignore_dlcs else {}
        dlcs[item_id] = ignored
        WishlistIgnoreRepository.update(ignore_record.id, ignore_dlcs=json.dumps(dlcs))
    else:
        return error_response(ErrorCode.INVALID_PARAMS, "Only dlc type is supported for ignore")

    # Invalidate per-user flattened cache so subsequent filtering sees new prefs
    try:
        from repositories.wishlistignore_repository import get_flattened_ignores_for_user

        get_flattened_ignores_for_user.cache_clear()
    except Exception:
        pass

    # Also update precomputed per-user title flags for this single title so
    # server-side filters that rely on user_title_flags stay in sync.
    try:
        from services.user_title_flags_service import compute_flags_for_user_title, upsert_user_title_flags
        from repositories.titles_repository import TitlesRepository

        # Build minimal apps list for the title
        t = TitlesRepository.get_by_title_id(title_id)
        if t is not None:
            apps = [
                {
                    "app_id": a.app_id,
                    "app_type": a.app_type.lower(),
                    "app_version": a.app_version,
                    "owned": a.owned,
                }
                for a in t.apps
            ]
            flags = compute_flags_for_user_title(current_user.id, title_id, apps)
            # Best-effort upsert; do not fail the request if DB/migration isn't ready
            try:
                upsert_user_title_flags(current_user.id, title_id, flags)
            except Exception:
                pass
    except Exception:
        # Do not let background sync errors affect API response
        pass

    return success_response(message="Ignore preference updated")


@wishlist_bp.route("/wishlist/ignore/<title_id>")
@login_required
@handle_api_errors
def get_wishlist_ignore(title_id):
    """Obtém preferências de ignore para um item da wishlist"""
    ignore_record = WishlistIgnoreRepository.get_by_user_and_title(current_user.id, title_id)

    if ignore_record:
        dlcs = json.loads(ignore_record.ignore_dlcs) if ignore_record.ignore_dlcs else {}
    else:
        dlcs = {}

    return success_response(data={"dlcs": dlcs})


@wishlist_bp.route("/wishlist/ignore")
@login_required
@handle_api_errors
def get_all_wishlist_ignore():
    """Obtém todas as preferências de ignore do usuário"""
    ignore_records = WishlistIgnoreRepository.get_all_by_user(current_user.id)

    result = {}
    for record in ignore_records:
        result[record.title_id] = {
            "dlcs": json.loads(record.ignore_dlcs) if record.ignore_dlcs else {}
        }

    return success_response(data=result)
