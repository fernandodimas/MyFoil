"""
Library Routes - Endpoints relacionados à biblioteca de jogos
"""

from flask import Blueprint, request, jsonify
from sqlalchemy import func, and_, case
from db import (
    db, Apps, Titles, Libraries, Files, get_libraries, logger, app_files,
    TitleMetadata, TitleTag, Tag, WishlistIgnore
)
from constants import APP_TYPE_BASE, APP_TYPE_UPD, APP_TYPE_DLC
from settings import load_settings
from auth import access_required
import titles
import titledb
import library
from utils import format_size_py

library_bp = Blueprint("library", __name__, url_prefix="/api")


@library_bp.route("/library")
@access_required("shop")
def library_api():
    """API endpoint da biblioteca com paginação - Otimizado"""
    # Fast check for cache and ETag
    cached = library.load_library_from_disk()
    if cached and "hash" in cached:
        etag = cached["hash"]
        if request.headers.get("If-None-Match") == etag:
            return "", 304

    # Paginação: obter parâmetros da query string
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 500, type=int)

    # Validar parâmetros
    page = max(1, page)  # Página mínima é 1
    MAX_PER_PAGE = 1000  # Limite máximo configurável
    per_page = min(max(1, per_page), MAX_PER_PAGE)  # Limitar ao máximo configurável

    lib_data = library.generate_library()
    total_items = len(lib_data)
    logger.info(f"Library API returning {total_items} items. Page: {page}, Per Page: {per_page}")

    # Calcular paginação
    total_pages = (total_items + per_page - 1) // per_page  # Ceiling division
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    # Aplicar paginação
    paginated_data = lib_data[start_idx:end_idx]

    # We need the hash for the header, so we reload from disk to get the full dict
    full_cache = library.load_library_from_disk()

    # Preparar resposta com metadados de paginação
    response_data = {
        "items": paginated_data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }

    resp = jsonify(response_data)
    if full_cache and "hash" in full_cache:
        resp.set_etag(full_cache["hash"])
        # Adicionar headers de paginação
        resp.headers["X-Total-Count"] = str(total_items)
        resp.headers["X-Page"] = str(page)
        resp.headers["X-Per-Page"] = str(per_page)
        resp.headers["X-Total-Pages"] = str(total_pages)
    return resp


@library_bp.route("/library/scroll")
@access_required("shop")
def library_scroll_api():
    """API endpoint para scroll infinito - Retorna batch de jogos"""
    # Parâmetros de scroll
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", 50, type=int)  # Batch size menor para scroll

    # Validar parâmetros
    offset = max(0, offset)
    limit = min(max(1, limit), 100)  # Limite de 100 por batch

    # Usar cache em memória se disponível
    lib_data = library.generate_library()
    total_items = len(lib_data)

    # Aplicar paginação
    batch_data = lib_data[offset : offset + limit]

    # Verificar se há mais dados
    has_more = offset + limit < total_items

    response_data = {
        "items": batch_data,
        "scroll": {
            "offset": offset,
            "limit": limit,
            "total_items": total_items,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
        },
    }

    return jsonify(response_data)


@library_bp.route("/library/ignore/<title_id>", methods=["GET", "POST"])
@access_required("shop")
def library_ignore_api(title_id):
    """Get or set per-item ignore preferences for a game (DLCs and Updates)"""
    from flask_login import current_user
    import json

    ignore_record = WishlistIgnore.query.filter_by(user_id=current_user.id, title_id=title_id).first()

    if request.method == "GET":
        if ignore_record:
            dlcs = json.loads(ignore_record.ignore_dlcs) if ignore_record.ignore_dlcs else {}
            updates = json.loads(ignore_record.ignore_updates) if ignore_record.ignore_updates else {}
        else:
            dlcs = {}
            updates = {}

        return jsonify({"success": True, "dlcs": dlcs, "updates": updates})

    data = request.json or {}
    item_type = data.get("type")  # 'dlc' or 'update'
    item_id = data.get("item_id")
    ignored = data.get("ignored", False)

    if not item_type or not item_id:
        return jsonify({"success": False, "error": "type and item_id are required"}), 400

    if item_type not in ("dlc", "update"):
        return jsonify({"success": False, "error": 'type must be "dlc" or "update"'}), 400

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


@library_bp.route("/library/<title_id>/status")
@access_required("shop")
def library_status_api(title_id):
    """Retorna status do jogo considerando preferências de ignore do usuário"""
    import json
    from flask_login import current_user
    import titles as titles_lib

    lib_data = library.load_library_from_disk()
    if not lib_data or "library" not in lib_data:
        return jsonify({"error": "Library not loaded"}), 500

    game = next((g for g in lib_data["library"] if g.get("id") == title_id), None)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    ignore_record = WishlistIgnore.query.filter_by(user_id=current_user.id, title_id=title_id).first()

    ignored_dlcs = json.loads(ignore_record.ignore_dlcs) if ignore_record and ignore_record.ignore_dlcs else {}
    ignored_updates = json.loads(ignore_record.ignore_updates) if ignore_record and ignore_record.ignore_updates else {}

    all_dlc_ids = titles_lib.get_all_existing_dlc(title_id) or []
    non_ignored_dlcs = [d for d in all_dlc_ids if not ignored_dlcs.get(str(d), False)]

    owned_dlc_ids = set()
    for app in game.get("apps", []):
        if app.get("app_type") == "DLC" and app.get("owned"):
            owned_dlc_ids.add(app.get("app_id"))

    available_but_not_owned_dlcs = [d for d in non_ignored_dlcs if d not in owned_dlc_ids]
    has_pending_dlcs = len(available_but_not_owned_dlcs) > 0 if non_ignored_dlcs else False

    ignored_updates_set = set(str(v) for v in ignored_updates.keys())
    latest_version = game.get("latest_version_available", 0)
    owned_version = game.get("owned_version", 0)

    if latest_version > 0 and owned_version < latest_version:
        next_version = owned_version + 1
        while next_version <= latest_version:
            if str(next_version) not in ignored_updates_set:
                has_pending_updates = True
                break
            next_version += 1
        else:
            has_pending_updates = False
    else:
        has_pending_updates = False

    return jsonify(
        {
            "title_id": title_id,
            "has_pending_dlcs": has_pending_dlcs,
            "has_pending_updates": has_pending_updates,
            "ignored_dlcs_count": len([d for d in ignored_dlcs.values() if d]),
            "ignored_updates_count": len([v for v in ignored_updates.values() if v]),
        }
    )


@library_bp.route("/library/search")
@access_required("shop")
def search_library_api():
    """Busca na biblioteca com filtros"""
    query = request.args.get("q", "").lower()
    genre = request.args.get("genre")
    owned_only = request.args.get("owned") == "true"
    missing_only = request.args.get("missing") == "true"
    up_to_date = request.args.get("up_to_date") == "true"
    pending = request.args.get("pending") == "true"

    lib_data = library.generate_library()

    results = []
    for game in lib_data:
        # Text search
        if query:
            name = (game.get("name") or "").lower()
            publisher = (game.get("publisher") or "").lower()
            tid = (game.get("id") or "").lower()
            if query not in name and query not in publisher and query not in tid:
                continue

        # Genre filter
        if genre and genre != "Todos os Gêneros":
            categories = game.get("category") or []
            if genre not in categories:
                continue

        # Ownership filters
        is_owned = game.get("have_base", False)
        if owned_only and not is_owned:
            continue
        if missing_only and is_owned:
            continue

        # Status filters
        is_up_to_date = game.get("up_to_date", False)
        if up_to_date and not is_up_to_date:
            continue

        has_pending = not is_up_to_date and is_owned
        if pending and not has_pending:
            continue

        results.append(game)

    return jsonify({"count": len(results), "results": results})


@library_bp.route("/library/outdated-games")
@access_required("shop")
def outdated_games_api():
    """
    API endpoint que retorna jogos com atualizações pendentes.
    
    Returns:
        JSON com lista de jogos que não possuem a última atualização disponível,
        incluindo informações sobre a versão pendente e data de lançamento.
    """
    # Pagination parameters
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    
    # Validate parameters
    limit = min(max(1, limit), 500)  # Max 500 per request
    offset = max(0, offset)
    
    try:
        # Query titles that are NOT up to date but HAVE the base game
        outdated_titles = Titles.query.filter(
            Titles.up_to_date == False,
            Titles.have_base == True
        ).limit(limit).offset(offset).all()
        
        # Get total count for pagination
        total_count = Titles.query.filter(
            Titles.up_to_date == False,
            Titles.have_base == True
        ).count()
        
        games_list = []
        for title in outdated_titles:
            try:
                # Get current owned version
                owned_apps = Apps.query.filter(
                    Apps.title_id == title.id,
                    Apps.owned == True
                ).all()
                
                current_version = max(
                    [app.app_version for app in owned_apps if app.app_version],
                    default=0
                )
                
                # Get pending update info
                pending_info = library.get_pending_update_info(title.title_id)
                
                if not pending_info:
                    # Skip if no update info available
                    continue
                
                # Only include if there's actually a newer version
                if pending_info["version"] <= current_version:
                    continue
                
                game_entry = {
                    "id": title.title_id,
                    "nsuid": title.nsuid or "Unknown",
                    "name": title.name or f"Unknown ({title.title_id})",
                    "current_version": current_version,
                    "current_version_string": library.version_to_string(current_version),
                    "pending_update": {
                        "version": pending_info["version"],
                        "version_string": pending_info["version_string"],
                        "update_id": pending_info["update_id"],
                        "release_date": pending_info["release_date"]
                    }
                }
                
                games_list.append(game_entry)
                
            except Exception as e:
                logger.error(f"Error processing outdated game {title.title_id}: {e}")
                continue
        
        return jsonify({
            "success": True,
            "count": len(games_list),
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "games": games_list
        })
        
    except Exception as e:
        logger.error(f"Error fetching outdated games: {e}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@library_bp.route("/stats/overview")
@access_required("shop")
def get_stats_overview():
    """Estatísticas detalhadas da biblioteca com filtros - Otimizado"""
    import library

    library_id = request.args.get("library_id", type=int)

    # 1. Fetch library list for filter dropdown
    libs = Libraries.query.all()
    libraries_list = [{"id": l.id, "path": l.path} for l in libs]

    # 2. Otimização: Combinar todas as queries de Files em uma única query com agregações
    if library_id:
        # Query otimizada usando join direto ao invés de subquery
        file_stats = (
            db.session.query(
                func.count(Files.id).label("total_files"),
                func.sum(Files.size).label("total_size"),
                func.sum(case((Files.identified == False, 1), else_=0)).label("unidentified_files"),
            )
            .filter(Files.library_id == library_id)
            .first()
        )

        # Query otimizada para Apps usando join direto
        Apps.query.join(app_files).join(Files).filter(Files.library_id == library_id)
    else:
        # Query otimizada sem filtro de library
        file_stats = db.session.query(
            func.count(Files.id).label("total_files"),
            func.sum(Files.size).label("total_size"),
            func.sum(case((Files.identified == False, 1), else_=0)).label("unidentified_files"),
        ).first()

    # Extrair resultados da query otimizada
    total_files = file_stats.total_files or 0
    total_size = file_stats.total_size or 0
    unidentified_files = file_stats.unidentified_files or 0
    identified_files = total_files - unidentified_files
    id_rate = round((identified_files / total_files * 100), 1) if total_files > 0 else 0

    # 4. Collection Breakdown (Owned Apps) - Otimizado com uma única query
    # Combinar todas as contagens em uma única query usando agregações condicionais
    if library_id:
        owned_apps_stats = (
            db.session.query(
                func.sum(case((Apps.owned == True, 1), else_=0)).label("total_owned"),
                func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_BASE), 1), else_=0)).label(
                    "total_bases"
                ),
                func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_UPD), 1), else_=0)).label(
                    "total_updates"
                ),
                func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_DLC), 1), else_=0)).label(
                    "total_dlcs"
                ),
                func.count(func.distinct(case((Apps.owned == True, Apps.title_id), else_=None))).label(
                    "distinct_titles"
                ),
            )
            .select_from(Apps)
            .join(app_files)
            .join(Files)
            .filter(Files.library_id == library_id)
            .first()
        )
    else:
        owned_apps_stats = (
            db.session.query(
                func.sum(case((Apps.owned == True, 1), else_=0)).label("total_owned"),
                func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_BASE), 1), else_=0)).label(
                    "total_bases"
                ),
                func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_UPD), 1), else_=0)).label(
                    "total_updates"
                ),
                func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_DLC), 1), else_=0)).label(
                    "total_dlcs"
                ),
                func.count(func.distinct(case((Apps.owned == True, Apps.title_id), else_=None))).label(
                    "distinct_titles"
                ),
            )
            .select_from(Apps)
            .first()
        )

    total_owned_bases = owned_apps_stats.total_bases or 0
    total_owned_updates = owned_apps_stats.total_updates or 0
    total_owned_dlcs = owned_apps_stats.total_dlcs or 0

    # 5. Up-to-date Logic (Requires Title level check)
    # This is more complex to filter strictly by library if a title bridges libraries,
    # but we'll use the TitleDB coverage logic globally for now.

    # Status breakdown (Global titles)
    # Note: We still use the library cache for genre and status for now if no filter
    # If filtered, we'll need to recalculate from DB or use a simplified logic
    lib_data = library.load_library_from_disk()
    if not lib_data:
        games = library.generate_library()
    else:
        games = lib_data.get("library", []) if isinstance(lib_data, dict) else lib_data

    # Filter games list if library_id provided (Heuristic)
    filtered_games = games
    if library_id:
        # A bit expensive, but accurate to the library
        lib_path = Libraries.query.get(library_id).path
        filtered_games = [g for g in games if any(lib_path in f for f in g.get("files", []))]

    # Recalculate based on filtered list
    # Total owned should be all games in our library list,
    # as items only appear there if we own at least one component (Base, Update or DLC)
    total_owned = len(filtered_games)
    up_to_date = len([g for g in filtered_games if g.get("status_color") == "green" and g.get("has_base")])
    # Genre Distribution (from filtered list)
    genre_dist = {}
    for g in filtered_games:
        cats = g.get("category", [])
        if not cats:
            cats = ["Unknown"]
        for c in cats:
            genre_dist[c] = genre_dist.get(c, 0) + 1

    # Coverage Logic: compare owned bases vs total available in TitleDB
    # We define "available" as any entry in TitleDBCache that ends with 000 (standard base TitleID rule)
    total_available_titledb = TitleDBCache.query.filter(TitleDBCache.title_id.like("%000")).count()

    # Recognized games are games we have that exist in TitleDB
    games_with_metadata = len(
        [g for g in filtered_games if g.get("name") and not g.get("name", "").startswith("Unknown")]
    )

    # Coverage relative to what we HAVE (metadata quality)
    metadata_coverage_pct = round((games_with_metadata / total_owned * 100), 1) if total_owned > 0 else 0

    # Global coverage (Discovery): what percentage of the full library do we own?
    # Consider only base games for a fair comparison
    global_coverage_pct = (
        round((total_owned_bases / total_available_titledb * 100), 2) if total_available_titledb > 0 else 0
    )

    app_settings = load_settings()
    keys_valid = app_settings.get("titles", {}).get("valid_keys", False)

    # TitleDB Info
    active_src = titledb.get_active_source_info()
    source_name = active_src.get("name", "Nenhuma") if active_src else "Nenhuma"

    return jsonify(
        {
            "libraries": libraries_list,
            "library": {
                "total_titles": len(filtered_games),
                "total_owned": total_owned,
                "total_bases": total_owned_bases,
                "total_updates": total_owned_updates,
                "total_dlcs": total_owned_dlcs,
                "total_size": total_size,
                "total_size_formatted": format_size_py(total_size),
                "up_to_date": up_to_date,
                "pending": total_owned - up_to_date,
                "completion_rate": round((up_to_date / total_owned * 100), 1) if total_owned > 0 else 0,
            },
            "titledb": {
                "total_available": total_available_titledb,
                "games_with_metadata": games_with_metadata,
                "coverage_pct": global_coverage_pct,
                "metadata_quality_pct": metadata_coverage_pct,
                "source_name": source_name,
            },
            "identification": {
                "total_files": total_files,
                "identified_pct": id_rate,
                "recognition_pct": metadata_coverage_pct,
                "unidentified_count": unidentified_files,
                "unrecognized_count": total_owned - games_with_metadata,
                "keys_valid": keys_valid,
            },
            "genres": genre_dist,
            "recent": filtered_games[:8],
        }
    )


@library_bp.route("/app_info/<id>")
@access_required("shop")
def app_info_api(id):
    """Informações detalhadas de um jogo específico"""
    # Try to get by TitleID first (hex string)
    tid = str(id).upper()
    title_obj = Titles.query.filter_by(title_id=tid).first()

    # If not found by TitleID, try by integer primary key (legacy/fallback)
    app_obj = None
    if not title_obj and str(id).isdigit():
        app_obj = db.session.get(Apps, int(id))
        if app_obj:
            tid = app_obj.title.title_id
            title_obj = app_obj.title

    if not title_obj:
        # Maybe it's a DLC app_id, try to find base TitleID
        titles.load_titledb()  # Ensure loaded
        base_tid, app_type = titles.identify_appId(tid)
        if base_tid and tid != base_tid:
            # It's a DLC or Update.
            # For the main game modal, we usually want the base_tid.
            # But let's check if we should stay on this ID
            if app_type == APP_TYPE_DLC:
                pass
            else:
                tid = base_tid
                title_obj = Titles.query.filter_by(title_id=tid).first()

    # If still not found, we can't show much, but let's try to show TitleDB info
    # if it's a valid TitleID even if not in our DB

    # Get basic info from titledb
    info = titles.get_game_info(tid)
    if not info:
        info = {
            "name": f"Unknown ({tid})",
            "publisher": "--",
            "description": "No information available.",
            "release_date": "--",
            "iconUrl": "/static/img/no-icon.png",
        }

    if not title_obj:
        # Game/Title not in our database as a main Title, or specifically a DLC request
        result = info.copy()
        result["id"] = tid
        result["app_id"] = tid
        result["owned_version"] = 0
        result["has_base"] = False
        result["has_latest_version"] = False
        result["has_all_dlcs"] = False
        result["owned"] = False

        # Files for this specific DLC if owned
        dlc_files = []
        app_obj_dlc = Apps.query.filter_by(app_id=tid, owned=True).first()
        if app_obj_dlc:
            result["owned"] = True
            for f in app_obj_dlc.files:
                dlc_files.append(
                    {
                        "id": f.id,
                        "filename": f.filename,
                        "filepath": f.filepath,
                        "size_formatted": format_size_py(f.size),
                    }
                )

        result["files"] = dlc_files
        result["updates"] = []
        result["dlcs"] = []
        result["category"] = info.get("category", [])
        return jsonify(result)

    # Get all apps for this title
    all_title_apps = library.get_all_title_apps(tid)

    # Base Files (from owned BASE apps)
    base_files = []
    base_apps = [a for a in all_title_apps if a["app_type"] == APP_TYPE_BASE and a["owned"]]
    for b in base_apps:
        # We need the original Files objects to get IDs for download
        app_model = db.session.get(Apps, b["id"])
        for f in app_model.files:
            base_files.append(
                {
                    "id": f.id,
                    "filename": f.filename,
                    "filepath": f.filepath,
                    "size": f.size,
                    "size_formatted": format_size_py(f.size),
                    "version": app_model.app_version,
                }
            )

    # Deduplicate files by ID
    seen_ids = set()
    unique_base_files = []
    seen_file_ids_in_modal = set()
    for f in base_files:
        if f["id"] not in seen_ids:
            unique_base_files.append(f)
            seen_ids.add(f["id"])
            seen_file_ids_in_modal.add(f["id"])

    # Updates and DLCs (for detailed listing)
    available_versions = titles.get_all_existing_versions(tid)
    # Updates list: Include ALL available versions from TitleDB
    version_release_dates = {v["version"]: v["release_date"] for v in available_versions}
    
    # Ensure v0 has the base game release date in YYYY-MM-DD format
    base_release_date = info.get("release_date", "")
    if base_release_date and len(str(base_release_date)) == 8 and str(base_release_date).isdigit():
        formatted_date = f"{str(base_release_date)[:4]}-{str(base_release_date)[4:6]}-{str(base_release_date)[6:]}"
        info["release_date"] = formatted_date
        version_release_dates[0] = formatted_date
    elif base_release_date:
        version_release_dates[0] = base_release_date
    else:
        version_release_dates[0] = "Unknown"

    update_apps = [a for a in all_title_apps if a["app_type"] == APP_TYPE_UPD]
    update_apps_by_version = {int(a.get("app_version") or 0): a for a in update_apps}
    
    updates_list = []
    # 1. Add all versions from TitleDB
    for v_info in available_versions:
        v_int = v_info["version"]
        if v_int == 0: continue
        
        upd_app = update_apps_by_version.get(v_int)
        files = []
        if upd_app and upd_app["owned"]:
            app_model = db.session.get(Apps, upd_app["id"])
            for f in app_model.files:
                if f.id in seen_file_ids_in_modal: continue
                files.append({"id": f.id, "filename": f.filename, "size_formatted": format_size_py(f.size)})
        
        updates_list.append({
            "version": v_int,
            "owned": upd_app["owned"] if upd_app else False,
            "release_date": v_info["release_date"] or "Unknown",
            "files": files
        })
        
    # 2. Add any owned updates not in TitleDB
    for v_int, upd_app in update_apps_by_version.items():
        if v_int not in [v["version"] for v in updates_list] and v_int != 0:
            files = []
            if upd_app["owned"]:
                app_model = db.session.get(Apps, upd_app["id"])
                for f in app_model.files:
                    if f.id in seen_file_ids_in_modal: continue
                    files.append({"id": f.id, "filename": f.filename, "size_formatted": format_size_py(f.size)})
            
            updates_list.append({
                "version": v_int,
                "owned": upd_app["owned"],
                "release_date": "Unknown",
                "files": files
            })

    # DLCs
    dlc_ids = titles.get_all_existing_dlc(tid)
    dlcs_list = []
    dlc_apps_grouped = {}
    for a in [a for a in all_title_apps if a["app_type"] == APP_TYPE_DLC]:
        aid = a["app_id"]
        if aid not in dlc_apps_grouped:
            dlc_apps_grouped[aid] = []
        dlc_apps_grouped[aid].append(a)

    for dlc_id in dlc_ids:
        # Filter out self-mappings
        if str(dlc_id).upper() == tid.upper():
            continue
            
        apps_for_dlc = dlc_apps_grouped.get(dlc_id, [])
        owned = any(a["owned"] for a in apps_for_dlc)
        files = []
        if owned:
            for a in apps_for_dlc:
                if a["owned"]:
                    app_model = db.session.get(Apps, a["id"])
                    for f in app_model.files:
                        files.append(
                            {
                                "id": f.id,
                                "filename": f.filename,
                                "filepath": f.filepath,
                                "size_formatted": format_size_py(f.size),
                            }
                        )

        dlc_info = titles.get_game_info(dlc_id)
        dlcs_list.append(
            {
                "app_id": dlc_id,
                "name": dlc_info.get("name", f"DLC {dlc_id}"),
                "owned": owned,
                "release_date": dlc_info.get("release_date", ""),
                "files": files,
            }
        )

    result = info.copy()
    result["id"] = tid
    result["app_id"] = tid
    result["title_id"] = tid

    # Ratings & Stats from Title object
    if title_obj:
        result["metacritic_score"] = title_obj.metacritic_score
        result["rawg_rating"] = title_obj.rawg_rating
        result["rating_count"] = title_obj.rating_count
        result["playtime_main"] = title_obj.playtime_main

        # Merge enriched metadata from TitleMetadata table
        remote_meta = TitleMetadata.query.filter_by(title_id=tid).all()
        for meta in remote_meta:
            if meta.rating and not result.get("metacritic_score"):
                result["metacritic_score"] = int(meta.rating)
            if meta.description and (
                not result.get("description") or len(meta.description) > len(result.get("description", ""))
            ):
                result["description"] = meta.description
            if meta.rating:
                result["rawg_rating"] = meta.rating / 20.0  # Convert back to 0-5 for UI consistency
            if meta.rating_count:
                result["rating_count"] = meta.rating_count

            # API Genres/Tags
            if meta.genres:
                result["category"] = list(set((result.get("category") or []) + (meta.genres or [])))
            if meta.tags:
                result["tags"] = list(set((result.get("tags") or []) + (meta.tags or [])))

            # Screenshots
            if meta.screenshots:
                existing_ss = set(s if isinstance(s, str) else s.get("url") for s in result.get("screenshots", []))
                for ss in meta.screenshots:
                    url = ss if isinstance(ss, str) else ss.get("url")
                    if url not in existing_ss:
                        result.setdefault("screenshots", []).append(ss)

        # Fallback to Title object fields if not updated by TitleMetadata
        if title_obj.genres_json:
            result["category"] = list(set((result.get("category") or []) + (title_obj.genres_json or [])))
        if title_obj.tags_json:
            result["tags"] = list(set((result.get("tags") or []) + (title_obj.tags_json or [])))
        if title_obj.screenshots_json:
            existing_ss = set(s if isinstance(s, str) else s.get("url") for s in result.get("screenshots", []))
            for ss in title_obj.screenshots_json:
                url = ss if isinstance(ss, str) else ss.get("url")
                if url not in existing_ss:
                    result.setdefault("screenshots", []).append(ss)

    # Include added_at for display in modal
    result["added_at"] = title_obj.added_at.isoformat() if title_obj and title_obj.added_at else None

    # Ensure screenshots are included
    result["screenshots"] = info.get("screenshots", [])

    # Calculate corrected owned version considering all owned apps (Base + Update)
    owned_versions = [int(a.get("app_version") or 0) for a in all_title_apps if a["owned"]]
    result["owned_version"] = max(owned_versions) if owned_versions else 0
    result["display_version"] = result["owned_version"]

    # Use status from title_obj (re-calculated with corrected logic in library.py/update_titles)
    result["has_base"] = title_obj.have_base
    result["has_latest_version"] = title_obj.up_to_date
    result["has_all_dlcs"] = title_obj.complete

    result["files"] = unique_base_files
    result["updates"] = sorted(updates_list, key=lambda x: x["version"])
    result["dlcs"] = sorted(dlcs_list, key=lambda x: x["name"])
    result["category"] = info.get("category", [])  # Genre/Categories

    # Total size for side info
    total_size = 0
    for a in all_title_apps:
        if a["owned"]:
            app_model = db.session.get(Apps, a["id"])
            for f in app_model.files:
                total_size += f.size

    result["size"] = total_size
    result["size_formatted"] = format_size_py(total_size)

    # Calculate status_color consistent with library list
    if result["has_base"] and (not result["has_latest_version"] or not result["has_all_dlcs"]):
        result["status_color"] = "orange"
    elif result["has_base"]:
        result["status_color"] = "green"
    else:
        result["status_color"] = "gray"

    # owned field for wishlist and other uses
    # Check both have_base and if there are actual files
    has_owned_files = len(unique_base_files) > 0
    result["owned"] = result["has_base"] or has_owned_files

    resp = jsonify(result)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@library_bp.route("/tags")
@access_required("shop")
def get_tags():
    """Get all available tags"""
    tags = Tag.query.all()
    return jsonify([{"id": t.id, "name": t.name, "color": t.color, "icon": t.icon} for t in tags])


@library_bp.route("/titles/<title_id>/tags")
@access_required("shop")
def get_title_tags(title_id):
    """Get tags for a specific title"""
    title = Titles.query.filter_by(title_id=title_id).first()
    if not title:
        return jsonify({"error": "Title not found"}), 404

    title_tags = TitleTag.query.filter_by(title_id=title_id).all()
    tag_ids = [tt.tag_id for tt in title_tags]
    tags = Tag.query.filter(Tag.id.in_(tag_ids)).all()

    return jsonify([{"id": t.id, "name": t.name, "color": t.color, "icon": t.icon} for t in tags])


@library_bp.route("/tags/<int:tag_id>", methods=["PUT"])
@access_required("admin")
def update_tag_api(tag_id):
    """Atualizar tag"""
    data = request.json
    tag = db.session.get(Tag, tag_id)
    if not tag:
        return jsonify({"error": "Tag not found"}), 404

    if "name" in data:
        tag.name = data["name"]
    if "color" in data:
        tag.color = data["color"]
    if "icon" in data:
        tag.icon = data["icon"]

    try:
        db.session.commit()
        return jsonify({"success": True, "tag": {"id": tag.id, "name": tag.name, "color": tag.color, "icon": tag.icon}})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@library_bp.route("/tags/<int:tag_id>", methods=["DELETE"])
@access_required("admin")
def delete_tag_api(tag_id):
    """Remover tag"""
    tag = db.session.get(Tag, tag_id)
    if not tag:
        return jsonify({"error": "Tag not found"}), 404

    try:
        db.session.delete(tag)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@library_bp.route("/library/metadata/refresh/<title_id>", methods=["POST"])
@access_required("shop")
def refresh_game_metadata(title_id):
    """Manually refresh metadata for a specific game"""
    from tasks import fetch_metadata_for_game_async

    game = Titles.query.filter_by(title_id=title_id).first()
    if not game:
        return jsonify({"error": "Game not found"}), 404

    # Queue async task
    fetch_metadata_for_game_async.delay(title_id)

    return jsonify({"message": "Metadata refresh queued", "title_id": title_id})


@library_bp.route("/library/metadata/refresh-all", methods=["POST"])
@access_required("admin")
def refresh_all_metadata():
    """Refresh metadata for all games (admin only)"""
    from tasks import fetch_metadata_for_all_games_async

    fetch_metadata_for_all_games_async.delay()

    return jsonify({"message": "Metadata refresh queued for all games"})


@library_bp.route("/library/search-rawg", methods=["GET"])
@access_required("admin")
def search_rawg_api():
    """Search RAWG API directly (for testing/manual matching)"""
    query = request.args.get("q")
    if not query:
        return jsonify({"error": "Query parameter 'q' required"}), 400

    from app_services.rating_service import RAWGClient

    settings = load_settings()
    api_key = settings.get("apis", {}).get("rawg_api_key")

    if not api_key:
        return jsonify({"error": "RAWG API key not configured"}), 500

    client = RAWGClient(api_key)
    try:
        result = client.search_game(query)
        return jsonify(result or {})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@library_bp.route("/library/search-igdb", methods=["GET"])
@access_required("admin")
def search_igdb_api():
    """Search IGDB API directly (for testing/manual matching)"""
    query = request.args.get("q")
    if not query:
        return jsonify({"error": "Query parameter 'q' required"}), 400

    from app_services.rating_service import IGDBClient

    settings = load_settings()
    client_id = settings.get("apis", {}).get("igdb_client_id")
    client_secret = settings.get("apis", {}).get("igdb_client_secret")

    if not client_id or not client_secret:
        return jsonify({"error": "IGDB credentials not configured"}), 500

    client = IGDBClient(client_id, client_secret)
    try:
        result = client.search_game(query)
        return jsonify(result or [])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
