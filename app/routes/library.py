"""
Library Routes - Endpoints relacionados à biblioteca de jogos
"""

from flask import Blueprint, request, jsonify
import hashlib
from sqlalchemy import func, and_, case, or_
from sqlalchemy.orm import joinedload
from db import (
    db,
    Apps,
    Titles,
    Libraries,
    Files,
    get_libraries,
    logger,
    app_files,
    TitleMetadata,
    TitleTag,
    Tag,
    WishlistIgnore,
    TitleDBCache,
    Wishlist,
)
from flask_login import current_user
from constants import APP_TYPE_BASE, APP_TYPE_UPD, APP_TYPE_DLC
from settings import load_settings
from auth import access_required
import titles
import titledb
import library
from utils import format_size_py, now_utc
import json

from api_responses import (
    success_response,
    error_response,
    handle_api_errors,
    ErrorCode,
    not_found_response,
    paginated_response,
)
from repositories.titles_repository import TitlesRepository
from repositories.apps_repository import AppsRepository
from repositories.libraries_repository import LibrariesRepository
from repositories.files_repository import FilesRepository
from repositories.wishlistignore_repository import WishlistIgnoreRepository
from repositories.tag_repository import TagRepository
from repositories.titletag_repository import TitleTagRepository
from repositories.wishlist_repository import WishlistRepository
from repositories.titledbcache_repository import TitleDBCacheRepository
from repositories.title_metadata_repository import TitleMetadataRepository

library_bp = Blueprint("library", __name__, url_prefix="/api")

# Import cache module (Phase 4.1)
try:
    import redis_cache

    CACHE_ENABLED = True
except ImportError:
    CACHE_ENABLED = False
    logger.warning("Redis cache module not available")


@library_bp.route("/library")
@access_required("shop")
@handle_api_errors
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

    # Support server-side simple filters for the dashboard cache endpoint
    # so clients can request filtered views without relying on potentially stale client-side logic.
    def _flag_true(v):
        return str(v).lower() in ("1", "true", "yes", "on")

    dlc_filter = _flag_true(request.args.get("dlc"))
    redundant_filter = _flag_true(request.args.get("redundant"))

    # lib_data is a list of game dicts
    filtered_lib = lib_data
    if dlc_filter:
        filtered_lib = [g for g in filtered_lib if g.get("has_base") and not g.get("has_all_dlcs")]
    if redundant_filter:
        filtered_lib = [g for g in filtered_lib if g.get("has_redundant_updates")]

    total_items = len(filtered_lib)
    logger.info(f"Library API returning {total_items} items. Page: {page}, Per Page: {per_page}")

    # Calcular paginação
    total_pages = (total_items + per_page - 1) // per_page  # Ceiling division
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    # Aplicar paginação
    paginated_data = filtered_lib[start_idx:end_idx]

    # We need the hash for the header, so we reload from disk to get the full dict
    full_cache = library.load_library_from_disk()

    # Preparar resposta com metadados de paginação
    data = {
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

    resp, status = success_response(data=data)
    if full_cache and "hash" in full_cache:
        resp.set_etag(full_cache["hash"])
        # Adicionar headers de paginação
        resp.headers["X-Total-Count"] = str(total_items)
        resp.headers["X-Page"] = str(page)
        resp.headers["X-Per-Page"] = str(per_page)
        resp.headers["X-Total-Pages"] = str(total_pages)
    return resp, status


def _serialize_title_with_apps(title: Titles) -> dict:
    """
    Serialize a title with its apps for the paginated library endpoint.
    Uses the library.get_game_info_item function for serialization.
    """
    from db import get_all_title_apps

    title_id = title.title_id

    # Get all title apps (owned and unowned)
    all_title_apps_dict = get_all_title_apps(title_id)

    # Get the full game object using the existing library function
    # This ensures consistency with the cached version
    game_info = library.get_game_info_item(
        title_id,
        {
            "title_id": title_id,
            "name": title.name,
            "iconUrl": title.icon_url,
            "bannerUrl": title.banner_url,
            "category": title.category,
            "release_date": title.release_date,
            "publisher": title.publisher,
            "description": title.description,
            "size": title.size,
            "nsuid": title.nsuid,
            "have_base": title.have_base,
            "up_to_date": title.up_to_date,
            "complete": title.complete,
            "apps": all_title_apps_dict,
        },
    )

    return game_info


@library_bp.route("/library/paged")
@access_required("shop")
@handle_api_errors
def library_paged_api():
    """
    Server-side paginated library endpoint (Phase 2.2).
    """
    # Parse parameters
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    # Accept both frontend param `sort_by` and legacy `sort` for compatibility
    sort_by = request.args.get("sort_by")
    if not sort_by:
        sort_by = request.args.get("sort", "name")
    order = request.args.get("order", "asc", type=str)

    # Validate parameters
    page = max(1, page)
    MAX_PER_PAGE = 100
    per_page = min(max(1, per_page), MAX_PER_PAGE)

    valid_sort_fields = ["name", "added_at", "release_date", "size"]
    if sort_by not in valid_sort_fields:
        sort_by = "name"

    if order not in ["asc", "desc"]:
        order = "asc"

    # Try to get from cache (Phase 4.1)
    if CACHE_ENABLED:
        cache_key = f"library_paged:{page}:{per_page}:{sort_by}:{order}"
        cached_data = redis_cache.cache_get(cache_key)
        if cached_data:
            # cached_data is a JSON string
            logger.debug(f"Cache HIT for library_paged: page={page}, sort={sort_by}-{order}")
            try:
                # Compute ETag from cached payload to support conditional GET
                etag = hashlib.md5(cached_data.encode("utf-8")).hexdigest()
                if request.headers.get("If-None-Match") == etag:
                    return "", 304

                data = json.loads(cached_data)
            except Exception:
                # If cached content is invalid, treat as cache miss
                logger.warning("Invalid cached payload, treating as cache miss")
                data = None

            if data is not None:
                resp = jsonify(data if isinstance(data, dict) else json.loads(data))
                resp.set_etag(etag)
                resp.headers["X-Cache"] = "HIT"
                resp.headers["X-Total-Count"] = str(data.get("pagination", {}).get("total_items", "0"))
                resp.headers["X-Page"] = str(page)
                resp.headers["X-Per-Page"] = str(per_page)
                resp.headers["Cache-Control"] = "public, max-age=300"
                return resp, 200

    # Use repository for pagination
    def _flag_true(v):
        return str(v).lower() in ("1", "true", "yes", "on")

    dlc_filter = _flag_true(request.args.get("dlc"))
    redundant_filter = _flag_true(request.args.get("redundant"))

    # If dlc or redundant filters are requested, do filtering at the serialization level
    # because the DB-level counters may be stale or conservative. We'll fetch a large
    # page of titles to process in memory and then paginate the filtered results.
    if dlc_filter or redundant_filter:
        # Fetch a large set (reasonable upper bound) to filter in memory
        FETCH_LIMIT = 5000
        paginated_all = TitlesRepository.get_paged(page=1, per_page=FETCH_LIMIT, sort_by=sort_by, order=order)
        all_titles = paginated_all.items

        items_all = []
        for title in all_titles:
            try:
                item = _serialize_title_with_apps(title)
                if not item:
                    continue

                # Apply requested post-serialization filters
                if dlc_filter:
                    # Wants games that have base but missing DLCs
                    if not (item.get("has_base") and not item.get("has_all_dlcs")):
                        continue
                if redundant_filter:
                    if not item.get("has_redundant_updates"):
                        continue

                items_all.append(item)
            except Exception as e:
                logger.error(f"Error serializing title {title.title_id}: {e}")
                continue

        # Manual pagination on filtered results
        total_items = len(items_all)
        total_pages = (total_items + per_page - 1) // per_page
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        items = items_all[start_idx:end_idx]

        data = {
            "items": items,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_items": total_items,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
                "sort_by": sort_by,
                "order": order,
            },
        }
    else:
        paginated = TitlesRepository.get_paged(page=page, per_page=per_page, sort_by=sort_by, order=order)

        # Serialize items
        items = []
        for title in paginated.items:
            try:
                item = _serialize_title_with_apps(title)
                if item:
                    items.append(item)
            except Exception as e:
                logger.error(f"Error serializing title {title.title_id}: {e}")
                continue

        # Build response data
        data = {
            "items": items,
            "pagination": {
                "page": paginated.page,
                "per_page": paginated.per_page,
                "total_items": paginated.total,
                "total_pages": paginated.pages,
                "has_next": paginated.has_next,
                "has_prev": paginated.has_prev,
                "sort_by": sort_by,
                "order": order,
            },
        }

    # Cache the response (Phase 4.1)
    if CACHE_ENABLED:
        try:
            # Ensure we store JSON string in cache for consistency
            redis_cache.cache_set(cache_key, json.dumps(data), ttl=300)  # 5 min cache
        except Exception as e:
            logger.warning(f"Failed to set cache for {cache_key}: {e}")

    # Build response payload with both envelope and top-level fields for compatibility
    response_payload = {
        "code": ErrorCode.SUCCESS,
        "success": True,
        "data": data,
        # include top-level shortcuts so older clients or different consumers can read items directly
        "items": data.get("items", []),
        "pagination": data.get("pagination", {}),
    }

    resp = jsonify(response_payload)
    resp.headers["X-Total-Count"] = str(paginated.total)
    resp.headers["X-Page"] = str(paginated.page)
    resp.headers["X-Per-Page"] = str(paginated.per_page)
    resp.headers["X-Total-Pages"] = str(paginated.pages)
    resp.headers["X-Cache"] = "MISS"
    resp.headers["Cache-Control"] = "public, max-age=300"  # 5 min cache
    return resp, 200


@library_bp.route("/library/search/paged")
@access_required("shop")
@handle_api_errors
def library_search_paged_api():
    """
    Server-side paginated search endpoint with pagination at DB level.
    """
    query_text = request.args.get("q", "").lower().strip()
    genre = request.args.get("genre")
    tag = request.args.get("tag")
    owned_only = request.args.get("owned") == "true"
    missing_only = request.args.get("missing") == "true"
    up_to_date = request.args.get("up_to_date") == "true"
    pending = request.args.get("pending") == "true"
    dlc = request.args.get("dlc") == "true"
    redundant = request.args.get("redundant") == "true"

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    page = max(1, page)
    MAX_PER_PAGE = 100
    per_page = min(max(1, per_page), MAX_PER_PAGE)

    # Use repository for pagination with filters
    filters = {
        "owned_only": owned_only,
        "up_to_date": up_to_date,
        "missing": missing_only,
        "pending": pending,
        "dlc": dlc,
        "redundant": redundant,
        "genre": genre,
        "tag": tag,
    }

    paginated = TitlesRepository.get_paged(
        page=page, per_page=per_page, query_text=query_text, filters=filters, sort_by="name", order="asc"
    )

    # Serialize items directly without secondary filtering
    items = []
    for title in paginated.items:
        try:
            item = _serialize_title_with_apps(title)
            if item:
                items.append(item)
        except Exception as e:
            logger.error(f"Error serializing title {title.title_id}: {e}")
            continue

    # Return paginated results directly from DB
    return success_response(
        data={
            "items": items,
            "pagination": {
                "page": paginated.page,
                "per_page": paginated.per_page,
                "total_items": paginated.total,
                "total_pages": paginated.pages,
                "has_next": paginated.has_next,
                "has_prev": paginated.has_prev,
            },
        }
    )


@library_bp.route("/library/scroll")
@access_required("shop")
@handle_api_errors
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

    data = {
        "items": batch_data,
        "scroll": {
            "offset": offset,
            "limit": limit,
            "total_items": total_items,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
        },
    }

    return success_response(data=data)


@library_bp.route("/library/ignore/<title_id>", methods=["GET", "POST"])
@access_required("shop")
@handle_api_errors
def library_ignore_api(title_id):
    """Get or set per-item ignore preferences for a game (DLCs and Updates)"""
    ignore_record = WishlistIgnoreRepository.get_by_user_and_title(current_user.id, title_id)

    if request.method == "GET":
        if ignore_record:
            dlcs = json.loads(ignore_record.ignore_dlcs) if ignore_record.ignore_dlcs else {}
            updates = json.loads(ignore_record.ignore_updates) if ignore_record.ignore_updates else {}
        else:
            dlcs = {}
            updates = {}

        return success_response(data={"dlcs": dlcs, "updates": updates})

    data = request.json or {}
    item_type = data.get("type")  # 'dlc' or 'update'
    item_id = data.get("item_id")
    ignored = data.get("ignored", False)

    if not item_type or not item_id:
        return error_response(ErrorCode.VALIDATION_ERROR, message="type and item_id are required", status_code=400)

    if item_type not in ("dlc", "update"):
        return error_response(ErrorCode.VALIDATION_ERROR, message='type must be "dlc" or "update"', status_code=400)

    if not ignore_record:
        ignore_record = WishlistIgnoreRepository.create(
            user_id=current_user.id, title_id=title_id, ignore_dlcs="{}", ignore_updates="{}"
        )

    if item_type == "dlc":
        dlcs = json.loads(ignore_record.ignore_dlcs) if ignore_record.ignore_dlcs else {}
        dlcs[item_id] = ignored
        WishlistIgnoreRepository.update(ignore_record.id, ignore_dlcs=json.dumps(dlcs))
    else:
        updates = json.loads(ignore_record.ignore_updates) if ignore_record.ignore_updates else {}
        updates[item_id] = ignored
        WishlistIgnoreRepository.update(ignore_record.id, ignore_updates=json.dumps(updates))

    return success_response(message="Ignore preferences updated")


@library_bp.route("/library/<title_id>/status")
@access_required("shop")
@handle_api_errors
def library_status_api(title_id):
    """Retorna status do jogo considerando preferências de ignore do usuário"""
    import titles as titles_lib

    lib_data = library.load_library_from_disk()
    if not lib_data or "library" not in lib_data:
        return error_response(ErrorCode.INTERNAL_ERROR, message="Library not loaded", status_code=500)

    game = next((g for g in lib_data["library"] if g.get("id") == title_id), None)
    if not game:
        return not_found_response("Game", title_id)

    ignore_record = WishlistIgnoreRepository.get_by_user_and_title(current_user.id, title_id)

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

    has_pending_updates = False
    if latest_version > 0 and owned_version < latest_version:
        next_version = owned_version + 1
        while next_version <= latest_version:
            if str(next_version) not in ignored_updates_set:
                has_pending_updates = True
                break
            next_version += 1

    return success_response(
        data={
            "title_id": title_id,
            "has_pending_dlcs": has_pending_dlcs,
            "has_pending_updates": has_pending_updates,
            "ignored_dlcs_count": len([d for d in ignored_dlcs.values() if d]),
            "ignored_updates_count": len([v for v in ignored_updates.values() if v]),
        }
    )


@library_bp.route("/library/search")
@access_required("shop")
@handle_api_errors
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

    return success_response(data={"count": len(results), "results": results})


@library_bp.route("/debug/library-dlc-report")
@access_required("shop")
@handle_api_errors
def debug_library_dlc_report():
    """Relatório diagnóstico para discrepâncias no filtro DLC/Redundant.

    Retorna contagens e exemplos usando (1) colunas materializadas em Titles,
    (2) flags 'complete' e (3) a versão construída em memória via generate_library().
    """
    from db import Files

    # 1) From Titles materialized counters
    try:
        rows_counter = (
            Titles.query.filter(Titles.have_base == True, func.coalesce(Titles.missing_dlcs_count, 0) > 0)
            .with_entities(Titles.title_id, Titles.name, Titles.missing_dlcs_count)
            .limit(200)
            .all()
        )
        counter_list = [{"title_id": r[0], "name": r[1], "missing_dlcs_count": int(r[2] or 0)} for r in rows_counter]
        counter_total = Titles.query.filter(
            Titles.have_base == True, func.coalesce(Titles.missing_dlcs_count, 0) > 0
        ).count()
    except Exception as e:
        counter_list = []
        counter_total = 0

    # 2) From 'complete' flag (have_base=True AND complete=False)
    try:
        rows_complete = (
            Titles.query.filter(Titles.have_base == True, Titles.complete == False)
            .with_entities(Titles.title_id, Titles.name)
            .limit(200)
            .all()
        )
        complete_list = [{"title_id": r[0], "name": r[1]} for r in rows_complete]
        complete_total = Titles.query.filter(Titles.have_base == True, Titles.complete == False).count()
    except Exception as e:
        complete_list = []
        complete_total = 0

    # 3) From in-memory generated library
    try:
        lib = library.generate_library()
        lib_missing = [g for g in lib if g.get("has_base") and not g.get("has_all_dlcs")]
        lib_redundant = [g for g in lib if g.get("has_redundant_updates")]
        lib_missing_examples = [{"title_id": g.get("title_id"), "name": g.get("name")} for g in lib_missing[:200]]
        lib_total_missing = len(lib_missing)
        lib_total_redundant = len(lib_redundant)
    except Exception as e:
        lib_missing_examples = []
        lib_total_missing = 0
        lib_total_redundant = 0

    # 4) For a few examples, fetch TitleDB known DLC count
    try:
        sample_titles = [x.get("title_id") for x in (counter_list[:5] or complete_list[:5] or lib_missing_examples[:5])]
        titledb_info = []
        for tid in sample_titles:
            if not tid:
                continue
            try:
                dlcs = titles.get_all_existing_dlc(tid) or []
            except Exception:
                dlcs = []
            titledb_info.append({"title_id": tid, "titledb_dlcs_count": len(dlcs), "titledb_dlcs": dlcs[:20]})
    except Exception:
        titledb_info = []

    return success_response(
        data={
            "titles_missing_by_counter_total": int(counter_total),
            "titles_missing_by_counter_examples": counter_list[:50],
            "titles_missing_by_complete_total": int(complete_total),
            "titles_missing_by_complete_examples": complete_list[:50],
            "library_missing_total": int(lib_total_missing),
            "library_missing_examples": lib_missing_examples,
            "library_redundant_total": int(lib_total_redundant),
            "titledb_sample_info": titledb_info,
        }
    )


@library_bp.route("/library/outdated-games")
@access_required("shop")
@handle_api_errors
def outdated_games_api():
    """
    API endpoint que retorna jogos com atualizações pendentes.
    """
    # Pagination parameters
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    # Validate parameters
    limit = min(max(1, limit), 500)  # Max 500 per request
    offset = max(0, offset)

    # Use repository to get outdated titles
    outdated_titles = TitlesRepository.get_outdated(limit=limit, offset=offset)
    total_count = TitlesRepository.count_outdated()

    games_list = []
    for title in outdated_titles:
        try:
            # Get current owned version
            owned_apps = AppsRepository.get_owned_by_title(title.id)
            current_version = max([app.app_version for app in owned_apps if app.app_version], default=0)

            # Get pending update info
            pending_info = library.get_pending_update_info(title.title_id)

            if not pending_info:
                continue

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
                    "release_date": pending_info["release_date"],
                },
            }

            games_list.append(game_entry)

        except Exception as e:
            logger.error(f"Error processing outdated game {title.title_id}: {e}")
            continue

    return success_response(
        data={
            "count": len(games_list),
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "games": games_list,
        }
    )


@library_bp.route("/stats/overview")
@access_required("shop")
@handle_api_errors
def get_stats_overview():
    """Estatísticas detalhadas da biblioteca com filtros - Otimizado"""
    library_id = request.args.get("library_id", type=int)

    # 1. Fetch library list for filter dropdown
    libs = LibrariesRepository.get_all()
    libraries_list = [{"id": l.id, "path": l.path} for l in libs]

    # 2. Otimização: Combinar todas as queries de Files em uma única query com agregações
    file_stats = FilesRepository.get_stats_by_library(library_id)

    # Extrair resultados da query otimizada
    total_files = file_stats["total_files"]
    total_size = file_stats["total_size"]
    unidentified_files = file_stats["unidentified_files"]
    identified_files = total_files - unidentified_files
    id_rate = round((identified_files / total_files * 100), 1) if total_files > 0 else 0

    # 3. Collection Breakdown (Owned Apps) - Otimizado com uma única query
    owned_apps_stats = AppsRepository.get_owned_counts(library_id)

    total_owned_bases = owned_apps_stats["bases"]
    total_owned_updates = owned_apps_stats["updates"]
    total_owned_dlcs = owned_apps_stats["dlcs"]

    # 4. Status breakdown and Genres (Logic from library cache)
    lib_data = library.load_library_from_disk()
    if not lib_data:
        games = library.generate_library()
    else:
        games = lib_data.get("library", []) if isinstance(lib_data, dict) else lib_data

    # Filter games list if library_id provided (Heuristic)
    filtered_games = games
    if library_id:
        # A bit expensive, but accurate to the library
        lib_obj = LibrariesRepository.get_by_id(library_id)
        if lib_obj:
            lib_path = lib_obj.path
            filtered_games = [g for g in games if any(lib_path in f for f in g.get("files", []))]

    # Recalculate based on filtered list
    total_owned = len(filtered_games)
    up_to_date = len([g for g in filtered_games if g.get("status_color") == "green" and g.get("has_base")])

    # Genre Distribution (from filtered list)
    genre_dist = {}
    for g in filtered_games:
        cats = g.get("category", []) or ["Unknown"]
        for c in cats:
            genre_dist[c] = genre_dist.get(c, 0) + 1

    # Sort genre distribution and take top 10
    genre_dist_sorted = dict(sorted(genre_dist.items(), key=lambda x: x[1], reverse=True)[:10])

    # Coverage Logic
    total_available_titledb = TitleDBCacheRepository.count_bases()

    # Recognized games are games we have that exist in TitleDB
    games_with_metadata = len(
        [g for g in filtered_games if g.get("name") and not g.get("name", "").startswith("Unknown")]
    )

    # Coverage relative to what we HAVE (metadata quality)
    metadata_coverage_pct = round((games_with_metadata / total_owned * 100), 1) if total_owned > 0 else 0

    # Global coverage (Discovery): what percentage of the full library do we own?
    global_coverage_pct = (
        round((total_owned_bases / total_available_titledb * 100), 2) if total_available_titledb > 0 else 0
    )

    # --- IGNORING LOGIC FOR PENDING COUNT ---
    pending_games = [g for g in filtered_games if g.get("status_color") != "green" and g.get("has_base")]
    ignored_games_count = 0

    if pending_games:
        ignores = WishlistIgnoreRepository.get_all_by_user(current_user.id)
        if ignores:
            ignore_map = {
                rec.title_id: {
                    "dlcs": json.loads(rec.ignore_dlcs or "{}"),
                    "updates": json.loads(rec.ignore_updates or "{}"),
                }
                for rec in ignores
            }

            for g in pending_games:
                tid = g.get("title_id")
                if not tid or tid not in ignore_map:
                    continue

                rec = ignore_map[tid]
                ignored_updates_set = set(str(k) for k, v in rec["updates"].items() if v)
                ignored_dlcs_set = set(str(k) for k, v in rec["dlcs"].items() if v)

                is_fully_ignored = True

                # Check Updates
                if not g.get("has_latest_version"):
                    current_ver = g.get("owned_version", 0)
                    avail_versions = titles.get_all_existing_versions(tid)
                    missing_versions = [v["version"] for v in avail_versions if v["version"] > current_ver]

                    for mv in missing_versions:
                        if str(mv) not in ignored_updates_set:
                            is_fully_ignored = False
                            break

                if not is_fully_ignored:
                    continue

                # Check DLCs
                if not g.get("has_all_dlcs"):
                    all_dlcs = titles.get_all_existing_dlc(tid)
                    owned_dlc_ids = set()
                    if g.get("apps"):
                        for a in g["apps"]:
                            if (
                                a.get("app_type") == APP_TYPE_DLC
                                and a.get("owned")
                                and len(a.get("files_info", [])) > 0
                            ):
                                owned_dlc_ids.add(a["app_id"].upper())

                    for dlc_id in all_dlcs:
                        dlc_id = dlc_id.upper()
                        if dlc_id == tid.upper():
                            continue

                        if dlc_id not in owned_dlc_ids:
                            if dlc_id not in ignored_dlcs_set:
                                is_fully_ignored = False
                                break

                if is_fully_ignored:
                    ignored_games_count += 1

    app_settings = load_settings()
    keys_valid = app_settings.get("titles", {}).get("valid_keys", False)

    # TitleDB Info
    active_src = titledb.get_active_source_info()
    source_name = active_src.get("name", "Nenhuma") if active_src else "Nenhuma"

    return success_response(
        data={
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
                "pending": max(0, (total_owned - up_to_date) - ignored_games_count),
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
            "genres": genre_dist_sorted,
            "recent": filtered_games[:8],
        }
    )


@library_bp.route("/app_info/<id>")
@access_required("shop")
@handle_api_errors
def app_info_api(id):
    """Informações detalhadas de um jogo específico"""
    logger.info(f"API: Requested app_info for {id} (v1626)")
    # Try to get by TitleID first (hex string)
    tid = str(id).upper()
    title_obj = TitlesRepository.get_by_title_id(tid)

    # If not found by TitleID, try by integer primary key (legacy/fallback)
    if not title_obj and str(id).isdigit():
        app_obj = AppsRepository.get_by_id(int(id))
        if app_obj and app_obj.title:
            tid = app_obj.title.title_id
            title_obj = app_obj.title

    # Handle phantom titles from Wishlist (upcoming/manual entries)
    if not title_obj and tid.startswith("UPCOMING_"):
        wish_item = WishlistRepository.get_by_title_id(tid)
        if wish_item:
            # Prepare genres and screenshots from wishlist item
            genres = []
            if wish_item.genres:
                genres = [g.strip() for g in wish_item.genres.split(",") if g.strip()]

            screenshots = []
            if wish_item.screenshots:
                try:
                    screenshots = json.loads(wish_item.screenshots)
                except:
                    # Fallback to comma separated if not JSON
                    screenshots = [s.strip() for s in wish_item.screenshots.split(",") if s.strip()]

            return success_response(
                data={
                    "id": tid,
                    "name": wish_item.name,
                    "publisher": "--",
                    "description": wish_item.description
                    or "Este jogo foi adicionado à sua wishlist a partir da lista de Próximos Lançamentos.",
                    "release_date": wish_item.release_date,
                    "iconUrl": wish_item.icon_url or "/static/img/no-icon.png",
                    "bannerUrl": wish_item.banner_url or "",
                    "owned": False,
                    "has_base": False,
                    "files": [],
                    "updates": [],
                    "dlcs": [],
                    "screenshots": screenshots,
                    "metacritic": None,
                    "rating": None,
                    "category": genres,
                }
            )

    if not title_obj:
        # Maybe it's a DLC app_id, try to find base TitleID
        titles.load_titledb()  # Ensure loaded
        base_tid, app_type = titles.identify_appId(tid)
        if base_tid and tid != base_tid:
            if app_type != APP_TYPE_DLC:
                tid = base_tid
                title_obj = TitlesRepository.get_by_title_id(tid)

    # Get basic info from titledb
    info = titles.get_game_info(tid)
    if not info:
        info = {
            "name": f"Unknown ({tid})",
            "publisher": "--",
            "description": "Informações não encontradas no TitleDB para este ID.",
            "release_date": "--",
            "iconUrl": "/static/img/no-icon.png",
        }

    if not title_obj:
        # Game/Title not in our database as a main Title, or specifically a DLC request
        result = info.copy()
        result.update(
            {
                "id": tid,
                "app_id": tid,
                "owned_version": 0,
                "has_base": False,
                "has_latest_version": False,
                "has_all_dlcs": False,
                "owned": False,
                "files": [],
                "updates": [],
                "dlcs": [],
                "category": info.get("category", []),
            }
        )

        # Apps associados mas sem Title record principal (ex: DLC avulsa)
        app_obj_extra = AppsRepository.get_by_app_id(tid, owned=True)
        if app_obj_extra:
            result["owned"] = True
            result["files"] = [
                {
                    "id": f.id,
                    "filename": f.filename,
                    "filepath": f.filepath,
                    "size_formatted": format_size_py(f.size),
                }
                for f in app_obj_extra.files
            ]

        return success_response(data=result)

    # Get all apps for this title
    all_title_apps = library.get_all_title_apps(tid)

    # Pre-calculate max version for each file ID across ALL apps for this title
    file_max_versions = {}
    owned_apps_map = [a for a in all_title_apps if a["owned"]]
    for a_meta in owned_apps_map:
        a_id = a_meta["id"]
        a_ver = int(a_meta["app_version"] or 0)
        app_db = AppsRepository.get_by_id(a_id)
        if app_db:
            for f in app_db.files:
                current = file_max_versions.get(f.id, 0)
                if a_ver > current:
                    file_max_versions[f.id] = a_ver

    # Base Files (from owned BASE apps)
    base_files = []
    base_apps = [a for a in all_title_apps if a["app_type"] == APP_TYPE_BASE and a["owned"]]
    for b in base_apps:
        app_model = AppsRepository.get_by_id(b["id"])
        if not app_model:
            continue
        for f in app_model.files:
            # Use the max calculated version for this file, or fallback to app version
            eff_version = file_max_versions.get(f.id, app_model.app_version)

            base_files.append(
                {
                    "id": f.id,
                    "filename": f.filename,
                    "filepath": f.filepath,
                    "size": f.size,
                    "size_formatted": format_size_py(f.size),
                    "version": eff_version,
                }
            )

    # Deduplicate files by ID
    seen_ids = set()
    unique_base_files = []
    for f in base_files:
        if f["id"] not in seen_ids:
            unique_base_files.append(f)
            seen_ids.add(f["id"])

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
        if v_int == 0:
            continue

        upd_app = update_apps_by_version.get(v_int)
        files = []
        if upd_app and upd_app["owned"]:
            app_model = AppsRepository.get_by_id(upd_app["id"])
            if app_model:
                for f in app_model.files:
                    files.append({"id": f.id, "filename": f.filename, "size_formatted": format_size_py(f.size)})

        updates_list.append(
            {
                "version": v_int,
                "owned": upd_app["owned"] if upd_app else False,
                "release_date": v_info["release_date"] or "Unknown",
                "files": files,
            }
        )

    # 2. Add any owned updates not in TitleDB
    for v_int, upd_app in update_apps_by_version.items():
        if v_int not in [v["version"] for v in updates_list] and v_int != 0:
            files = []
            if upd_app.get("owned"):
                app_model = AppsRepository.get_by_id(upd_app["id"])
                if app_model:
                    for f in app_model.files:
                        files.append({"id": f.id, "filename": f.filename, "size_formatted": format_size_py(f.size)})

            updates_list.append(
                {"version": v_int, "owned": upd_app.get("owned", False), "release_date": "Unknown", "files": files}
            )

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
                if a.get("owned"):
                    app_model = AppsRepository.get_by_id(a["id"])
                    if app_model:
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

        # Merge enriched metadata
        remote_meta = TitleMetadataRepository.get_by_title_id(tid)
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
                existing_ss = set(
                    s if isinstance(s, str) else (s.get("url") if s else None)
                    for s in (result.get("screenshots") or [])
                )
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
            existing_ss = set(
                s if isinstance(s, str) else (s.get("url") if s else None) for s in (result.get("screenshots") or [])
            )
            for ss in title_obj.screenshots_json:
                url = ss if isinstance(ss, str) else ss.get("url")
                if url not in existing_ss:
                    result.setdefault("screenshots", []).append(ss)

    # Include added_at for display in modal
    result["added_at"] = title_obj.added_at.isoformat() if title_obj and title_obj.added_at else None

    # Ensure screenshots are initialized if missing
    if result.get("screenshots") is None:
        result["screenshots"] = []

    # Calculate corrected owned version considering all owned apps (Base + Update)
    owned_versions = [int(a.get("app_version") or 0) for a in all_title_apps if a["owned"]]
    result["owned_version"] = max(owned_versions) if owned_versions else 0
    result["display_version"] = result["owned_version"]

    # Use status from title_obj
    result["has_base"] = title_obj.have_base if title_obj else False
    result["has_latest_version"] = title_obj.up_to_date if title_obj else False
    result["has_all_dlcs"] = title_obj.complete if title_obj else False

    result["files"] = unique_base_files
    result["updates"] = sorted(updates_list, key=lambda x: x["version"])
    result["dlcs"] = sorted(dlcs_list, key=lambda x: x["name"])
    result["category"] = result.get("category") or info.get("category", [])  # Genre/Categories

    # Total size for side info
    total_size = 0
    for a in all_title_apps:
        if a["owned"]:
            app_model = AppsRepository.get_by_id(a["id"])
            if app_model:
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
    has_owned_files = len(unique_base_files) > 0
    result["owned"] = result["has_base"] or has_owned_files

    return success_response(data=result)


@library_bp.route("/tags")
@access_required("shop")
@handle_api_errors
def get_tags():
    """Get all available tags"""
    tags = TagRepository.get_all()
    return success_response(data=[{"id": t.id, "name": t.name, "color": t.color, "icon": t.icon} for t in tags])


@library_bp.route("/titles/<title_id>/tags")
@access_required("shop")
@handle_api_errors
def get_title_tags(title_id):
    """Get tags for a specific title"""
    title = TitlesRepository.get_by_title_id(title_id)
    if not title:
        return not_found_response("Title not found")

    title_tags = TitleTagRepository.get_by_title_id(title_id)
    tag_ids = [tt.tag_id for tt in title_tags]
    tags = TagRepository.get_by_ids(tag_ids)

    return success_response(data=[{"id": t.id, "name": t.name, "color": t.color, "icon": t.icon} for t in tags])


@library_bp.route("/tags/<int:tag_id>", methods=["PUT"])
@access_required("admin")
@handle_api_errors
def update_tag_api(tag_id):
    """Atualizar tag"""
    data = request.json
    tag = TagRepository.update(tag_id, **data)
    if not tag:
        return not_found_response("Tag not found")
    return success_response(data={"id": tag.id, "name": tag.name, "color": tag.color, "icon": tag.icon})


@library_bp.route("/tags/<int:tag_id>", methods=["DELETE"])
@access_required("admin")
@handle_api_errors
def delete_tag_api(tag_id):
    """Remover tag"""
    if TagRepository.delete(tag_id):
        return success_response(message="Tag removed successfully")
    return not_found_response("Tag not found")


@library_bp.route("/library/metadata/refresh/<title_id>", methods=["POST"])
@access_required("shop")
@handle_api_errors
def refresh_game_metadata(title_id):
    """Manually refresh metadata for a specific game"""
    from tasks import fetch_metadata_for_game_async

    game = TitlesRepository.get_by_title_id(title_id)
    if not game:
        return not_found_response("Game not found")

    # Queue async task
    fetch_metadata_for_game_async.delay(title_id)

    return success_response(message="Metadata refresh queued", data={"title_id": title_id})


@library_bp.route("/library/metadata/refresh-all", methods=["POST"])
@access_required("admin")
@handle_api_errors
def refresh_all_metadata():
    """Refresh metadata for all games (admin only)"""
    from tasks import fetch_metadata_for_all_games_async

    fetch_metadata_for_all_games_async.delay()

    return success_response(message="Metadata refresh queued for all games")


@library_bp.route("/library/search-rawg", methods=["GET"])
@access_required("admin")
@handle_api_errors
def search_rawg_api():
    """Search RAWG API directly (for testing/manual matching)"""
    query = request.args.get("q")
    if not query:
        return error_response(ErrorCode.INVALID_PARAMS, "Query parameter 'q' required")

    from app_services.rating_service import RAWGClient

    settings = load_settings()
    api_key = settings.get("apis", {}).get("rawg_api_key")

    if not api_key:
        return error_response(ErrorCode.INTERNAL_ERROR, "RAWG API key not configured")

    client = RAWGClient(api_key)
    result = client.search_game(query)
    return success_response(data=result or {})


@library_bp.route("/library/search-igdb", methods=["GET"])
@access_required("admin")
@handle_api_errors
def search_igdb_api():
    """Search IGDB API directly (for testing/manual matching)"""
    query = request.args.get("q")
    if not query:
        return error_response(ErrorCode.INVALID_PARAMS, "Query parameter 'q' required")

    from app_services.rating_service import IGDBClient

    settings = load_settings()
    client_id = settings.get("apis", {}).get("igdb_client_id")
    client_secret = settings.get("apis", {}).get("igdb_client_secret")

    if not client_id or not client_secret:
        return error_response(ErrorCode.INTERNAL_ERROR, "IGDB credentials not configured")

    client = IGDBClient(client_id, client_secret)
    result = client.search_game(query)
    return success_response(data=result or [])
