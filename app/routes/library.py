"""
Library Routes - Endpoints relacionados à biblioteca de jogos
"""
from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user
from sqlalchemy import func, and_, case
from db import *
from db import app_files
from settings import load_settings
from auth import access_required
import titles
import library
from utils import format_size_py

library_bp = Blueprint('library', __name__, url_prefix='/api')

@library_bp.route('/library')
@access_required('shop')
def library_api():
    """API endpoint da biblioteca com paginação - Otimizado"""
    # Fast check for cache and ETag
    cached = library.load_library_from_disk()
    if cached and 'hash' in cached:
        etag = cached['hash']
        if request.headers.get('If-None-Match') == etag:
            return '', 304

    # Paginação: obter parâmetros da query string
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)

    # Validar parâmetros
    page = max(1, page)  # Página mínima é 1
    per_page = max(1, per_page)  # Sem limite máximo

    # generate_library will use cache if force=False (default)
    lib_data = library.generate_library()
    total_items = len(lib_data)

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
        'items': paginated_data,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total_items': total_items,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1
        }
    }

    resp = jsonify(response_data)
    if full_cache and 'hash' in full_cache:
        resp.set_etag(full_cache['hash'])
        # Adicionar headers de paginação
        resp.headers['X-Total-Count'] = str(total_items)
        resp.headers['X-Page'] = str(page)
        resp.headers['X-Per-Page'] = str(per_page)
        resp.headers['X-Total-Pages'] = str(total_pages)
    return resp

@library_bp.route('/library/search')
@access_required('shop')
def search_library_api():
    """Busca na biblioteca com filtros"""
    query = request.args.get('q', '').lower()
    genre = request.args.get('genre')
    owned_only = request.args.get('owned') == 'true'
    missing_only = request.args.get('missing') == 'true'
    up_to_date = request.args.get('up_to_date') == 'true'
    pending = request.args.get('pending') == 'true'

    lib_data = library.generate_library()

    results = []
    for game in lib_data:
        # Text search
        if query:
            name = (game.get('name') or '').lower()
            publisher = (game.get('publisher') or '').lower()
            tid = (game.get('id') or '').lower()
            if query not in name and query not in publisher and query not in tid:
                continue

        # Genre filter
        if genre and genre != 'Todos os Gêneros':
            categories = game.get('category') or []
            if genre not in categories:
                continue

        # Ownership filters
        is_owned = game.get('have_base', False)
        if owned_only and not is_owned:
            continue
        if missing_only and is_owned:
            continue

        # Status filters
        is_up_to_date = game.get('up_to_date', False)
        if up_to_date and not is_up_to_date:
            continue

        has_pending = not is_up_to_date and is_owned
        if pending and not has_pending:
            continue

        results.append(game)

    return jsonify({
        'count': len(results),
        'results': results[:100]  # Limit to 100 for performance
    })

@library_bp.route('/stats/overview')
@access_required('shop')
def get_stats_overview():
    """Estatísticas detalhadas da biblioteca com filtros - Otimizado"""
    import titles
    import library
    from sqlalchemy import func, case, and_

    library_id = request.args.get('library_id', type=int)

    # 1. Fetch library list for filter dropdown
    libs = Libraries.query.all()
    libraries_list = [{'id': l.id, 'path': l.path} for l in libs]

    # 2. Otimização: Combinar todas as queries de Files em uma única query com agregações
    if library_id:
        # Query otimizada usando join direto ao invés de subquery
        file_stats = db.session.query(
            func.count(Files.id).label('total_files'),
            func.sum(Files.size).label('total_size'),
            func.sum(case((Files.identified == False, 1), else_=0)).label('unidentified_files')
        ).filter(Files.library_id == library_id).first()

        # Query otimizada para Apps usando join direto
        apps_query = Apps.query.join(app_files).join(Files).filter(Files.library_id == library_id)
    else:
        # Query otimizada sem filtro de library
        file_stats = db.session.query(
            func.count(Files.id).label('total_files'),
            func.sum(Files.size).label('total_size'),
            func.sum(case((Files.identified == False, 1), else_=0)).label('unidentified_files')
        ).first()

        apps_query = Apps.query

    # Extrair resultados da query otimizada
    total_files = file_stats.total_files or 0
    total_size = file_stats.total_size or 0
    unidentified_files = file_stats.unidentified_files or 0
    identified_files = total_files - unidentified_files
    id_rate = round((identified_files / total_files * 100), 1) if total_files > 0 else 0

    # 4. Collection Breakdown (Owned Apps) - Otimizado com uma única query
    # Combinar todas as contagens em uma única query usando agregações condicionais
    if library_id:
        owned_apps_stats = db.session.query(
            func.sum(case((Apps.owned == True, 1), else_=0)).label('total_owned'),
            func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_BASE), 1), else_=0)).label('total_bases'),
            func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_UPD), 1), else_=0)).label('total_updates'),
            func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_DLC), 1), else_=0)).label('total_dlcs'),
            func.count(func.distinct(case((Apps.owned == True, Apps.title_id), else_=None))).label('distinct_titles')
        ).select_from(Apps).join(app_files).join(Files).filter(Files.library_id == library_id).first()
    else:
        owned_apps_stats = db.session.query(
            func.sum(case((Apps.owned == True, 1), else_=0)).label('total_owned'),
            func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_BASE), 1), else_=0)).label('total_bases'),
            func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_UPD), 1), else_=0)).label('total_updates'),
            func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_DLC), 1), else_=0)).label('total_dlcs'),
            func.count(func.distinct(case((Apps.owned == True, Apps.title_id), else_=None))).label('distinct_titles')
        ).select_from(Apps).first()

    total_owned_bases = owned_apps_stats.total_bases or 0
    total_owned_updates = owned_apps_stats.total_updates or 0
    total_owned_dlcs = owned_apps_stats.total_dlcs or 0
    total_owned_distinct_titles = owned_apps_stats.distinct_titles or 0

    # 5. Up-to-date Logic (Requires Title level check)
    # This is more complex to filter strictly by library if a title bridges libraries,
    # but we'll use the TitleDB coverage logic globally for now.
    all_titles_count = Titles.query.count()  # Total in database
    titles_db_count = titles.get_titles_count()

    # Status breakdown (Global titles)
    # Note: We still use the library cache for genre and status for now if no filter
    # If filtered, we'll need to recalculate from DB or use a simplified logic
    lib_data = library.load_library_from_disk()
    if not lib_data:
        games = library.generate_library()
    else:
        games = lib_data.get('library', []) if isinstance(lib_data, dict) else lib_data

    # Filter games list if library_id provided (Heuristic)
    filtered_games = games
    if library_id:
        # A bit expensive, but accurate to the library
        lib_path = Libraries.query.get(library_id).path
        filtered_games = [g for g in games if any(lib_path in f for f in g.get('files', []))]

    # Recalculate based on filtered list
    # Total owned should be all games in our library list,
    # as items only appear there if we own at least one component (Base, Update or DLC)
    total_owned = len(filtered_games)
    up_to_date = len([g for g in filtered_games if g.get('status_color') == 'green' and g.get('has_base')])
    # Genre Distribution (from filtered list)
    genre_dist = {}
    for g in filtered_games:
        cats = g.get('category', [])
        if not cats: cats = ['Unknown']
        for c in cats:
            genre_dist[c] = genre_dist.get(c, 0) + 1

    # Recognition Logic (Check if the TitleID exists in TitleDB and has a name)
    # Titles are considered unrecognized if their name starts with "Unknown" or if they are purely generic
    recognized_games = len([g for g in filtered_games if g.get('name') and not g.get('name', '').startswith('Unknown')])
    recognition_rate = round((recognized_games / total_owned * 100), 1) if total_owned > 0 else 0

    coverage_pct = round((total_owned / titles_db_count * 100), 2) if titles_db_count > 0 else 0
    app_settings = load_settings()
    keys_valid = app_settings.get('titles', {}).get('valid_keys', False)

    # TitleDB Info
    active_src = titledb.get_active_source_info()
    source_name = active_src.get('name', 'Nenhuma') if active_src else 'Nenhuma'

    return jsonify({
        'libraries': libraries_list,
        'library': {
            'total_titles': len(filtered_games),
            'total_owned': total_owned,
            'total_bases': total_owned_bases,
            'total_updates': total_owned_updates,
            'total_dlcs': total_owned_dlcs,
            'total_size': total_size,
            'total_size_formatted': format_size_py(total_size),
            'up_to_date': up_to_date,
            'pending': total_owned - up_to_date,
            'completion_rate': round((up_to_date / total_owned * 100), 1) if total_owned > 0 else 0
        },
        'titledb': {
            'total_available': titles_db_count,
            'coverage_pct': coverage_pct,
            'source_name': source_name
        },
        'identification': {
            'total_files': total_files,
            'identified_pct': id_rate,
            'recognition_pct': recognition_rate,
            'unidentified_count': unidentified_files,
            'unrecognized_count': total_owned - recognized_games,
            'keys_valid': keys_valid
        },
        'genres': genre_dist,
        'recent': filtered_games[:8]
    })

@library_bp.route('/app_info/<id>')
@access_required('shop')
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

    is_dlc_request = False
    if not title_obj:
        # Maybe it's a DLC app_id, try to find base TitleID
        titles.load_titledb()  # Ensure loaded
        base_tid, app_type = titles.identify_appId(tid)
        if base_tid and tid != base_tid:
             # It's a DLC or Update.
             # For the main game modal, we usually want the base_tid.
             # But let's check if we should stay on this ID
             if app_type == APP_TYPE_DLC:
                 is_dlc_request = True
             else:
                 tid = base_tid
                 title_obj = Titles.query.filter_by(title_id=tid).first()

    # If still not found, we can't show much, but let's try to show TitleDB info
    # if it's a valid TitleID even if not in our DB

    # Get basic info from titledb
    info = titles.get_game_info(tid)
    if not info:
        info = {
            'name': f'Unknown ({tid})',
            'publisher': '--',
            'description': 'No information available.',
            'release_date': '--',
            'iconUrl': '/static/img/no-icon.png'
        }

    if not title_obj:
        # Game/Title not in our database as a main Title, or specifically a DLC request
        result = info.copy()
        result['id'] = tid
        result['app_id'] = tid
        result['owned_version'] = 0
        result['has_base'] = False
        result['has_latest_version'] = False
        result['has_all_dlcs'] = False
        result['owned'] = False

        # Files for this specific DLC if owned
        dlc_files = []
        app_obj_dlc = Apps.query.filter_by(app_id=tid, owned=True).first()
        if app_obj_dlc:
            result['owned'] = True
            for f in app_obj_dlc.files:
                dlc_files.append({
                    'id': f.id,
                    'filename': f.filename,
                    'filepath': f.filepath,
                    'size_formatted': format_size_py(f.size)
                })

        result['files'] = dlc_files
        result['updates'] = []
        result['dlcs'] = []
        result['category'] = info.get('category', [])
        return jsonify(result)

    # Get all apps for this title
    all_title_apps = library.get_all_title_apps(tid)

    # Base Files (from owned BASE apps)
    base_files = []
    base_apps = [a for a in all_title_apps if a['app_type'] == APP_TYPE_BASE and a['owned']]
    for b in base_apps:
        # We need the original Files objects to get IDs for download
        app_model = db.session.get(Apps, b['id'])
        for f in app_model.files:
            base_files.append({
                'id': f.id,
                'filename': f.filename,
                'filepath': f.filepath,
                'size': f.size,
                'size_formatted': format_size_py(f.size),
                'version': app_model.app_version
            })

    # Deduplicate files by ID
    seen_ids = set()
    unique_base_files = []
    seen_file_ids_in_modal = set()
    for f in base_files:
        if f['id'] not in seen_ids:
            unique_base_files.append(f)
            seen_ids.add(f['id'])
            seen_file_ids_in_modal.add(f['id'])

    # Updates and DLCs (for detailed listing)
    available_versions = titles.get_all_existing_versions(tid)
    version_release_dates = {v['version']: v['release_date'] for v in available_versions}

    # Ensure v0 has the base game release date in YYYY-MM-DD format
    base_release_date = info.get('release_date', '')
    if base_release_date and len(str(base_release_date)) == 8 and str(base_release_date).isdigit():
        # Format YYYYMMDD to YYYY-MM-DD
        formatted_date = f"{str(base_release_date)[:4]}-{str(base_release_date)[4:6]}-{str(base_release_date)[6:]}"
        # Update info for the main response
        info['release_date'] = formatted_date
        # Set for v0
        version_release_dates[0] = formatted_date
    elif base_release_date:
        version_release_dates[0] = base_release_date


    update_apps = [a for a in all_title_apps if a['app_type'] == APP_TYPE_UPD]
    updates_list = []
    for upd in update_apps:
        v_int = int(upd['app_version'])
        if v_int == 0: continue  # Skip base version in updates history

        # Get file IDs for owned updates
        files = []
        if upd['owned']:
            app_model = db.session.get(Apps, upd['id'])
            for f in app_model.files:
                if f.id in seen_file_ids_in_modal:
                    continue
                files.append({'id': f.id, 'filename': f.filename, 'size_formatted': format_size_py(f.size)})

        updates_list.append({
            'version': v_int,
            'owned': upd['owned'],
            'release_date': version_release_dates.get(v_int, 'Unknown'),
            'files': files
        })

    # DLCs
    dlc_ids = titles.get_all_existing_dlc(tid)
    dlcs_list = []
    dlc_apps_grouped = {}
    for a in [a for a in all_title_apps if a['app_type'] == APP_TYPE_DLC]:
        aid = a['app_id']
        if aid not in dlc_apps_grouped: dlc_apps_grouped[aid] = []
        dlc_apps_grouped[aid].append(a)

    for dlc_id in dlc_ids:
        apps_for_dlc = dlc_apps_grouped.get(dlc_id, [])
        owned = any(a['owned'] for a in apps_for_dlc)
        files = []
        if owned:
            for a in apps_for_dlc:
                if a['owned']:
                    app_model = db.session.get(Apps, a['id'])
                    for f in app_model.files:
                        files.append({
                            'id': f.id,
                            'filename': f.filename,
                            'filepath': f.filepath,
                            'size_formatted': format_size_py(f.size)
                        })

        dlc_info = titles.get_game_info(dlc_id)
        dlcs_list.append({
            'app_id': dlc_id,
            'name': dlc_info.get('name', f'DLC {dlc_id}'),
            'owned': owned,
            'release_date': dlc_info.get('release_date', ''),
            'files': files  # Includes filename and id, let's ensure filepath is there too if needed
        })

    result = info.copy()
    result['id'] = tid
    result['app_id'] = tid
    result['title_id'] = tid

    # Calculate corrected owned version considering all owned apps (Base + Update)
    owned_versions = [int(a['app_version']) for a in all_title_apps if a['owned']]
    result['owned_version'] = max(owned_versions) if owned_versions else 0
    result['display_version'] = result['owned_version']

    # Use status from title_obj (re-calculated with corrected logic in library.py/update_titles)
    result['has_base'] = title_obj.have_base
    result['has_latest_version'] = title_obj.up_to_date
    result['has_all_dlcs'] = title_obj.complete

    result['files'] = unique_base_files
    result['updates'] = sorted(updates_list, key=lambda x: x['version'])
    result['dlcs'] = sorted(dlcs_list, key=lambda x: x['name'])
    result['category'] = info.get('category', [])  # Genre/Categories

    # Total size for side info
    total_size = 0
    for a in all_title_apps:
        if a['owned']:
            app_model = db.session.get(Apps, a['id'])
            for f in app_model.files:
                total_size += f.size

    result['size'] = total_size
    result['size_formatted'] = format_size_py(total_size)

    # Calculate status_color consistent with library list
    if result['has_base'] and (not result['has_latest_version'] or not result['has_all_dlcs']):
         result['status_color'] = 'orange'
    elif result['has_base']:
         result['status_color'] = 'green'
    else:
         result['status_color'] = 'gray'

    return jsonify(result)

@library_bp.route('/tags')
@access_required('shop')
def get_tags():
    """Get all available tags"""
    tags = Tag.query.all()
    return jsonify([{
        'id': t.id,
        'name': t.name,
        'color': t.color,
        'icon': t.icon
    } for t in tags])

@library_bp.route('/titles/<title_id>/tags')
@access_required('shop')
def get_title_tags(title_id):
    """Get tags for a specific title"""
    title = Titles.query.filter_by(title_id=title_id).first()
    if not title:
        return jsonify({'error': 'Title not found'}), 404
    
    title_tags = TitleTag.query.filter_by(title_id=title_id).all()
    tag_ids = [tt.tag_id for tt in title_tags]
    tags = Tag.query.filter(Tag.id.in_(tag_ids)).all()
    
    return jsonify([{
        'id': t.id,
        'name': t.name,
        'color': t.color,
        'icon': t.icon
    } for t in tags])