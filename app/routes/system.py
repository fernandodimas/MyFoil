"""
System Routes - Endpoints relacionados ao sistema (stats, backups, etc.)
"""
from flask import Blueprint, render_template, request, jsonify, Response
from flask_login import current_user
from db import *
from settings import load_settings
from auth import access_required, admin_account_created
import titles
import titledb
import json
from utils import format_size_py
from metrics import generate_latest, CONTENT_TYPE_LATEST
from i18n import get_build_version

system_bp = Blueprint('system', __name__, url_prefix='/api')

# Web routes (não-API)
system_web_bp = Blueprint('system_web', __name__)

@system_web_bp.route('/stats')
@access_required('shop')
def stats_page():
    """Página de estatísticas"""
    return render_template('stats.html', title='Statistics', build_version=get_build_version())

@system_web_bp.route('/settings')
@access_required('admin')
def settings_page():
    """Página de configurações"""
    languages = {}
    try:
        languages_path = os.path.join(TITLEDB_DIR, 'languages.json')
        if os.path.exists(languages_path):
            with open(languages_path) as f:
                languages = json.load(f)
                languages = dict(sorted(languages.items()))
    except Exception as e:
        logger.warning(f"Could not load languages.json: {e}")

    return render_template(
        'settings.html',
        title='Settings',
        languages_from_titledb=languages,
        admin_account_created=admin_account_created(),
        valid_keys=load_settings()['titles']['valid_keys'],
        active_source=titledb.get_active_source_info(),
        build_version=get_build_version())

@system_bp.route('/metrics')
def metrics():
    """Endpoint de métricas Prometheus"""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

@system_bp.route('/system/info')
@access_required('shop')
def system_info_api():
    """Informações do sistema"""
    from settings import load_settings
    from i18n import get_build_version
    settings = load_settings()

    # Get detailed source info
    source_info = titledb.get_active_source_info()
    source_name = source_info.get('name', 'TitleDB') if source_info else 'TitleDB'

    titledb_file = titles.get_loaded_titles_file()

    # Check what update source we are using
    update_src = "TitleDB (versions.json)"

    # Identification source - show Source Name + Region File
    if titledb_file != "None":
        id_src = f"{source_name} ({titledb_file})"
    else:
        id_src = f"{source_name} (Não carregado)"

    return jsonify({
        'build_version': get_build_version(),
        'id_source': id_src,
        'update_source': update_src,
        'titledb_region': settings.get('titles/region', 'US'),
        'titledb_language': settings.get('titles/language', 'en'),
        'titledb_file': titledb_file
    })

@system_bp.route('/set_language/<lang>', methods=['POST'])
def set_language(lang):
    """Definir idioma da interface"""
    if lang in ['en', 'pt_BR']:
        resp = jsonify({'success': True})
        # Set cookie for 1 year
        resp.set_cookie('language', lang, max_age=31536000)
        return resp
    return jsonify({'success': False, 'error': 'Invalid language'}), 400

@system_bp.route('/library/scan')
@access_required('admin')
def scan_library_api():
    """Iniciar scan da biblioteca"""
    data = request.json or {}
    path = data.get('path')

    from app import CELERY_ENABLED
    from tasks import scan_library_async, scan_all_libraries_async

    success = True
    errors = []

    import app
    with app.scan_lock:
        if app.scan_in_progress:
            logger.info('Skipping scan_library_api call: Scan already in progress')
            return jsonify({'success': False, 'errors': []})
        app.scan_in_progress = True

    try:
        if CELERY_ENABLED:
            if path is None:
                scan_all_libraries_async.delay()
                logger.info("Triggered asynchronous full library scan.")
            else:
                scan_library_async.delay(path)
                logger.info(f"Triggered asynchronous library scan for: {path}")
            return jsonify({'success': True, 'async': True, 'errors': []})
        else:
            from library import scan_library_path, scan_library
            if path is None:
                scan_library()
            else:
                scan_library_path(path)
            from library import post_library_change
            post_library_change()
            return jsonify({'success': True, 'async': False, 'errors': []})
    except Exception as e:
        errors.append(str(e))
        success = False
        logger.error(f"Error during library scan: {e}")
    finally:
        if not CELERY_ENABLED:
            with app.scan_lock:
                app.scan_in_progress = False
    resp = {
        'success': success,
        'errors': errors
    }
    return jsonify(resp)

@system_bp.route('/files/unidentified')
@access_required('admin')
def get_unidentified_files_api():
    """Obter arquivos não identificados"""
    import titles
    # 1. Arquivos sem TitleID (Falha técnica de identificação)
    files = get_all_unidentified_files()
    results = [{
        'id': f.id,
        'filename': f.filename,
        'filepath': f.filepath,
        'size': f.size,
        'size_formatted': format_size_py(f.size),
        'error': f.identification_error or 'Arquivo não identificado (ID ausente)'
    } for f in files]

    # 2. Arquivos com TitleID mas sem reconhecimento de nome (Unknown)
    # Buscamos por arquivos que pertencem a jogos "Unknown" no TitleDB
    identified_files = Files.query.filter(Files.identified == True).all()
    for f in identified_files:
        if not f.apps:
            continue

        # Pega o primeiro app associado (normalmente arquivos NSP/XCI pertencem a 1 app)
        try:
            tid = f.apps[0].title.title_id
            tinfo = titles.get_title_info(tid)
            name = tinfo.get('name', '')

            # Se for desconhecido (começa com Unknown ou vazio)
            if not name or name.startswith('Unknown'):
                results.append({
                    'id': f.id,
                    'filename': f.filename,
                    'filepath': f.filepath,
                    'size': f.size,
                    'size_formatted': format_size_py(f.size),
                    'error': f'Título não reconhecido no Banco de Dados ({tid})'
                })
        except (IndexError, AttributeError):
            continue

    return jsonify(results)

@system_bp.route('/files/all')
@access_required('admin')
def get_all_files_api():
    """Obter todos os arquivos"""
    files = Files.query.order_by(Files.filename).all()
    results = []
    for f in files:
        title_id = None
        title_name = None
        if f.apps and len(f.apps) > 0:
            try:
                title_id = f.apps[0].title.title_id
                title_info = titles.get_title_info(title_id)
                title_name = title_info.get('name', 'Unknown') if title_info else 'Unknown'
            except (IndexError, AttributeError):
                pass
        
        ext = ''
        if f.filename:
            parts = f.filename.rsplit('.', 1)
            if len(parts) > 1:
                ext = parts[1].lower()
        
        results.append({
            'id': f.id,
            'filename': f.filename,
            'filepath': f.filepath,
            'size': f.size,
            'size_formatted': format_size_py(f.size),
            'extension': ext,
            'identified': f.identified,
            'identification_error': f.identification_error,
            'title_id': title_id,
            'title_name': title_name
        })
    
    return jsonify(results)

@system_bp.route('/files/delete/<int:file_id>', methods=['POST'])
@access_required('admin')
def delete_file_api(file_id):
    """Deletar arquivo específico"""
    try:
        # Find associated TitleID before deletion for cache update
        file_obj = db.session.get(Files, file_id)
        if not file_obj:
            return jsonify({'success': False, 'error': 'File not found'}), 404

        title_ids = []
        if file_obj.apps:
            title_ids = list(set([a.title.title_id for a in file_obj.apps if a.title]))

        from library import delete_file_from_db_and_disk
        success, error = delete_file_from_db_and_disk(file_id)

        if success:
            logger.info(f"File {file_id} deleted. Updating cache for titles: {title_ids}")
            # Invalidate full library cache to ensure consistency
            from library import invalidate_library_cache
            invalidate_library_cache()
            for tid in title_ids:
                try:
                    from library import update_game_in_cache
                    update_game_in_cache(tid)
                except Exception as ex:
                    logger.error(f"Error updating cache for title {tid}: {ex}")
        else:
            logger.warning(f"File deletion failed for {file_id}: {error}")

        return jsonify({'success': success, 'error': error})
    except Exception as e:
        logger.exception(f"Unhandled error in delete_file_api: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@system_bp.route('/titledb/search')
@access_required('shop')
def search_titledb_api():
    """Buscar no TitleDB"""
    query = request.args.get('q', '').lower()
    if not query or len(query) < 2:
        return jsonify([])

    results = titles.search_titledb_by_name(query)
    return jsonify(results[:20])  # Limit to 20 results

@system_bp.route('/status')
def process_status_api():
    """Status do sistema"""
    import app
    return jsonify({
        'scanning': app.scan_in_progress,
        'updating_titledb': app.is_titledb_update_running
    })

@system_bp.post('/settings/titledb/update')
@access_required('admin')
def force_titledb_update_api():
    """Forçar atualização do TitleDB"""
    from app import update_titledb_job
    import threading
    threading.Thread(target=update_titledb_job, args=(True,)).start()
    return jsonify({
        'success': True,
        'message': 'Update started in background'
    })

@system_bp.post('/settings/titledb/sources/reorder')
@access_required('admin')
def titledb_sources_reorder_api():
    """Reordenar prioridades das fontes TitleDB"""
    import titledb_sources
    data = request.json
    if not data:
        return jsonify({'success': False, 'errors': ['No data provided']})

    manager = titledb_sources.TitleDBSourceManager()
    success = manager.update_priorities(data)
    return jsonify({
        'success': success,
        'errors': [] if success else ['Failed to update priorities']
    })

@system_bp.post('/settings/titledb/sources/refresh-dates')
@access_required('admin')
def refresh_titledb_sources_dates_api():
    """Atualizar datas remotas das fontes TitleDB"""
    import titledb_sources
    manager = titledb_sources.TitleDBSourceManager()
    manager.refresh_remote_dates()
    return jsonify({'success': True})

@system_bp.route('/titles', methods=['GET'])
@access_required('shop')
def get_all_titles_api():
    """Obter todos os títulos"""
    from library import generate_library
    titles_library = generate_library()

    return jsonify({
        'total': len(titles_library),
        'games': titles_library
    })

@system_bp.route('/games/<tid>/custom', methods=['GET'])
@access_required('shop')
def get_game_custom_info(tid):
    """Obter informações customizadas do jogo"""
    info = titles.get_custom_title_info(tid)
    return jsonify({'success': True, 'data': info})

@system_bp.route('/games/<tid>/custom', methods=['POST'])
@access_required('shop')
def update_game_custom_info(tid):
    """Atualizar informações customizadas do jogo"""
    data = request.json
    success, error = titles.save_custom_title_info(tid, data)

    if success:
        # Invalidate library cache so the new info appears immediately
        from library import invalidate_library_cache
        invalidate_library_cache()
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': error}), 500

@system_bp.route('/webhooks')
@access_required('admin')
def get_webhooks_api():
    """Obter webhooks configurados"""
    webhooks = Webhook.query.all()
    return jsonify([w.to_dict() for w in webhooks])

@system_bp.post('/webhooks')
@access_required('admin')
def add_webhook_api():
    """Adicionar webhook"""
    data = request.json
    import json
    webhook = Webhook(
        url=data['url'],
        events=json.dumps(data.get('events', ['library_updated'])),
        secret=data.get('secret'),
        active=data.get('active', True)
    )
    db.session.add(webhook)
    try:
        db.session.commit()
        from app import log_activity
        log_activity('webhook_created', details={'url': webhook.url}, user_id=current_user.id)
        return jsonify({'success': True, 'webhook': webhook.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@system_bp.delete('/webhooks/<int:id>')
@access_required('admin')
def delete_webhook_api(id):
    """Remover webhook"""
    webhook = db.session.get(Webhook, id)
    if webhook:
        db.session.delete(webhook)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Webhook not found'}), 404

@system_bp.post('/backup/create')
@access_required('admin')
def create_backup_api():
    """Criar backup manual"""
    import app
    if not app.backup_manager:
        return jsonify({'success': False, 'error': 'Backup manager not initialized'}), 500

    success, timestamp = app.backup_manager.create_backup()
    if success:
        return jsonify({
            'success': True,
            'timestamp': timestamp,
            'message': 'Backup created successfully'
        })
    else:
        return jsonify({'success': False, 'error': 'Backup failed'}), 500

@system_bp.get('/backup/list')
@access_required('admin')
def list_backups_api():
    """Listar backups disponíveis"""
    import app
    if not app.backup_manager:
        return jsonify({'success': False, 'error': 'Backup manager not initialized'}), 500

    backups = app.backup_manager.list_backups()
    return jsonify({
        'success': True,
        'backups': backups
    })

@system_bp.post('/backup/restore')
@access_required('admin')
def restore_backup_api():
    """Restaurar backup"""
    import app
    if not app.backup_manager:
        return jsonify({'success': False, 'error': 'Backup manager not initialized'}), 500

    data = request.json
    filename = data.get('filename')

    if not filename:
        return jsonify({'success': False, 'error': 'Filename required'}), 400

    success = app.backup_manager.restore_backup(filename)
    if success:
        return jsonify({
            'success': True,
            'message': f'Restored from {filename}. Please restart the application.'
        })
    else:
        return jsonify({'success': False, 'error': 'Restore failed'}), 500

@system_bp.route('/activity', methods=['GET'])
@access_required('admin')
def activity_api():
    """Obter log de atividades"""
    limit = request.args.get('limit', 50, type=int)
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(limit).all()

    import json
    results = []
    for l in logs:
        results.append({
            'timestamp': l.timestamp.isoformat(),
            'action': l.action_type,
            'title_id': l.title_id,
            'user': l.user_id,  # Simplified
            'details': json.loads(l.details) if l.details else {}
        })
    return jsonify(results)

@system_bp.route('/plugins', methods=['GET'])
@access_required('admin')
def plugins_api():
    """Obter lista de plugins"""
    from app import plugin_manager
    if not plugin_manager:
        return jsonify([])

    # Return all discovered plugins with their enabled status
    return jsonify(plugin_manager.discovered_plugins)

@system_bp.post('/plugins/toggle')
@access_required('admin')
def toggle_plugin_api():
    """Alternar status do plugin"""
    data = request.json
    plugin_id = data.get('id')
    enabled = data.get('enabled', True)

    if not plugin_id:
        return jsonify({'error': 'Plugin ID required'}), 400

    # 1. Update settings file
    import settings
    settings.toggle_plugin_settings(plugin_id, enabled)

    # 2. Reload plugins in the manager to reflect changes
    # Note: This won't "unload" already loaded classes from memory, but will
    # stop them from being active if reload logic is implemented correctly.
    # For now, it updates the discovered_plugins list and future events will skip it.
    from app import plugin_manager
    disabled_plugins = load_settings(force=True).get('plugins', {}).get('disabled', [])
    plugin_manager.load_plugins(disabled_plugins)

    return jsonify({'success': True})

@system_bp.route('/cloud/auth/<provider>', methods=['GET'])
@access_required('admin')
def cloud_auth_api(provider):
    """Autenticação com provedor de nuvem"""
    from app import cloud_manager
    if not cloud_manager:
        return jsonify({'error': 'Cloud manager not initialized'}), 500

    redirect_uri = request.host_url.rstrip('/') + f'/api/cloud/callback/{provider}'
    auth_url = cloud_manager.get_auth_url(provider, redirect_uri)

    if not auth_url:
        return jsonify({'error': 'Provider not configured or disabled'}), 400

    return jsonify({'auth_url': auth_url})

@system_bp.route('/cloud/callback/<provider>', methods=['GET', 'POST'])
def cloud_callback_api(provider):
    """Callback de autenticação com nuvem"""
    from app import cloud_manager
    # This endpoint receives the code from Google
    if request.method == 'GET':
        code = request.args.get('code')
        error = request.args.get('error')
        if error:
            return f"Error: {error}"

        if code:
            redirect_uri = request.host_url.rstrip('/') + f'/api/cloud/callback/{provider}'
            if cloud_manager.authenticate(provider, code, redirect_uri):
                return "Authentication successful! You can close this window."
            else:
                return "Authentication failed.", 500

    # POST for manual code entry if needed
    data = request.json
    code = data.get('code')
    redirect_uri = data.get('redirect_uri')

    if cloud_manager.authenticate(provider, code, redirect_uri):
        return jsonify({'success': True})
    return jsonify({'success': False}), 400

@system_bp.route('/cloud/status', methods=['GET'])
@access_required('admin')
def cloud_status_api():
    """Status da integração com nuvem"""
    from app import cloud_manager
    if not cloud_manager:
        return jsonify({})

    results = {}
    for name, provider in cloud_manager.providers.items():
        results[name] = {
            'configured': True,
            'authenticated': (hasattr(provider, 'creds') and provider.creds is not None) or \
                             (hasattr(provider, 'access_token') and provider.access_token is not None)
        }
    return jsonify(results)

@system_bp.route('/cloud/files/<provider>', methods=['GET'])
@access_required('admin')
def cloud_files_api(provider):
    """Listar arquivos na nuvem"""
    from app import cloud_manager
    folder_id = request.args.get('folder_id')
    files = cloud_manager.list_files(provider, folder_id)
    return jsonify({'files': files})