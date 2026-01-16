"""
Settings Routes - Endpoints relacionados às configurações do sistema
"""
from flask import Blueprint, render_template, request, jsonify, redirect, current_app
from flask_login import current_user
from db import *
from settings import *
from auth import access_required
import os
import json

settings_bp = Blueprint('settings', __name__, url_prefix='/api')

@settings_bp.route('/settings')
@access_required('admin')
def get_settings_api():
    """Obter configurações atuais"""
    reload_conf()
    settings = copy.deepcopy(current_app.app_settings)

    # Flatten settings for the JS frontend
    flattened = {}
    for section, values in settings.items():
        if isinstance(values, dict):
            for key, value in values.items():
                flattened[f"{section}/{key}"] = value
        else:
            flattened[section] = values

    # Tinfoil Auth specific handling
    if settings.get('shop', {}).get('hauth'):
        flattened['shop/hauth'] = True
    else:
        flattened['shop/hauth'] = False

    return jsonify(flattened)

@settings_bp.post('/settings/titles')
@access_required('admin')
def set_titles_settings_api():
    """Atualizar configurações de títulos"""
    settings = request.json
    current_settings = load_settings()

    region = settings.get('region', current_settings['titles'].get('region', 'US'))
    language = settings.get('language', current_settings['titles'].get('language', 'en'))
    dbi_versions = settings.get('dbi_versions', current_settings['titles'].get('dbi_versions', False))

    languages_path = os.path.join(TITLEDB_DIR, 'languages.json')
    if os.path.exists(languages_path):
        with open(languages_path) as f:
            languages = json.load(f)
            languages = dict(sorted(languages.items()))

        if region not in languages or language not in languages[region]:
            resp = {
                'success': False,
                'errors': [{
                        'path': 'titles',
                        'error': f"The region/language pair {region}/{language} is not available."
                    }]
            }
            return jsonify(resp)

    set_titles_settings(region, language, dbi_versions)
    reload_conf()

    # Run update in background
    from app import update_titledb_job
    import threading
    threading.Thread(target=update_titledb_job, args=(True,)).start()

    resp = {
        'success': True,
        'errors': []
    }
    return jsonify(resp)

@settings_bp.route('/settings/regions')
@access_required('admin')
def get_regions_api():
    """Obter lista de regiões disponíveis"""
    languages_path = os.path.join(TITLEDB_DIR, 'languages.json')
    if not os.path.exists(languages_path):
        return jsonify({'regions': []})
    try:
        with open(languages_path) as f:
            languages = json.load(f)
        return jsonify({'regions': sorted(list(languages.keys()))})
    except:
        return jsonify({'regions': []})

@settings_bp.route('/settings/languages')
@access_required('admin')
def get_languages_api():
    """Obter lista de idiomas disponíveis"""
    languages_path = os.path.join(TITLEDB_DIR, 'languages.json')
    if not os.path.exists(languages_path):
        return jsonify({'languages': []})
    try:
        with open(languages_path) as f:
            languages = json.load(f)
        all_langs = set()
        for region_langs in languages.values():
            all_langs.update(region_langs)
        return jsonify({'languages': sorted(list(all_langs))})
    except:
        return jsonify({'languages': []})

@settings_bp.route('/settings/renaming', methods=['GET', 'POST'])
@access_required('admin')
def renaming_settings_api():
    """Gerenciar configurações de renomeação"""
    if request.method == 'POST':
        data = request.json
        settings = load_settings()
        if 'renaming' not in settings:
            settings['renaming'] = {}

        settings['renaming']['enabled'] = data.get('enabled', False)
        settings['renaming']['pattern_base'] = data.get('pattern_base', '{Name} [{TitleID}] [v{Version}]')
        settings['renaming']['pattern_upd'] = data.get('pattern_upd', '{Name} [UPD] [{TitleID}] [v{Version}]')
        settings['renaming']['pattern_dlc'] = data.get('pattern_dlc', '{Name} [DLC] [{TitleID}] [v{Version}]')

        with open(CONFIG_FILE, 'w') as yaml_file:
            yaml.dump(settings, yaml_file)
        reload_conf()

        return jsonify({'success': True})

    settings = load_settings()
    renaming = settings.get('renaming', DEFAULT_SETTINGS['renaming'])
    return jsonify({'success': True, 'settings': renaming})

@settings_bp.post('/settings/shop')
def set_shop_settings_api():
    """Atualizar configurações da loja"""
    data = request.json
    set_shop_settings(data)
    reload_conf()
    resp = {
        'success': True,
        'errors': []
    }
    return jsonify(resp)

@settings_bp.route('/settings/library/paths', methods=['GET', 'POST', 'DELETE'])
@access_required('admin')
def library_paths_api():
    """Gerenciar caminhos da biblioteca"""
    from app import watcher
    if request.method == 'POST':
        data = request.json
        from library import add_library_complete
        success, errors = add_library_complete(app, watcher, data['path'])
        if success:
            reload_conf()
            from library import post_library_change
            post_library_change()
        resp = {
            'success': success,
            'errors': errors
        }
    elif request.method == 'GET':
        reload_conf()
        libs = Libraries.query.all()
        paths_info = []
        for l in libs:
            # Files in this library
            files_count = Files.query.filter_by(library_id=l.id).count()
            total_size = db.session.query(func.sum(Files.size)).filter_by(library_id=l.id).scalar() or 0

            # Identified titles (approximate by distinct apps)
            # We join to get title_id from Apps linked to files in this library
            try:
                titles_query = db.session.query(Apps.title_id).distinct().join(app_files).join(Files).filter(Files.library_id == l.id)
                titles_count = titles_query.count()
            except Exception as e:
                logger.error(f"Error counting titles for path {l.path}: {e}")
                titles_count = 0

            paths_info.append({
                'id': l.id,
                'path': l.path,
                'files_count': files_count,
                'total_size': total_size,
                'total_size_formatted': format_size_py(total_size),
                'titles_count': titles_count,
                'last_scan': l.last_scan.strftime("%Y-%m-%d %H:%M:%S") if l.last_scan else "Nunca"
            })

        resp = {
            'success': True,
            'errors': [],
            'paths': paths_info
        }
    elif request.method == 'DELETE':
        data = request.json
        from library import remove_library_complete
        success, errors = remove_library_complete(app, watcher, data['path'])
        if success:
            reload_conf()
            from library import post_library_change
            post_library_change()
        resp = {
            'success': success,
            'errors': errors
        }
    return jsonify(resp)

@settings_bp.post('/settings/keys')
@access_required('admin')
def set_keys_api():
    """Atualizar arquivo de chaves"""
    from utils import allowed_file
    from settings import KEYS_FILE

    errors = []
    success = False

    file = request.files['file']
    if file and allowed_file(file.filename):
        # filename = secure_filename(file.filename)
        file.save(KEYS_FILE + '.tmp')
        logger.info(f'Validating {file.filename}...')
        from nstools.nut import Keys
        valid = Keys.load(KEYS_FILE + '.tmp')
        if valid:
            os.rename(KEYS_FILE + '.tmp', KEYS_FILE)
            success = True
            logger.info('Successfully saved valid keys.txt')
            reload_conf()
            from library import post_library_change
            post_library_change()
        else:
            os.remove(KEYS_FILE + '.tmp')
            logger.error(f'Invalid keys from {file.filename}')

    resp = {
        'success': success,
        'errors': errors
    }
    return jsonify(resp)

@settings_bp.route('/settings/titledb/sources', methods=['GET', 'POST', 'PUT', 'DELETE'])
@access_required('admin')
def titledb_sources_api():
    """Gerenciar fontes do TitleDB"""
    import titledb_sources
    if request.method == 'GET':
        # Get all sources and their status
        sources = titledb_sources.TitleDBSourceManager().get_sources_status()
        return jsonify({
            'success': True,
            'sources': sources
        })

    elif request.method == 'POST':
        # Add a new source
        data = request.json
        name = data.get('name')
        base_url = data.get('base_url')
        priority = data.get('priority', 50)
        enabled = data.get('enabled', True)
        source_type = data.get('source_type', 'json')

        if not name or not base_url:
            return jsonify({
                'success': False,
                'errors': ['Name and base_url are required']
            })

        manager = titledb_sources.TitleDBSourceManager()
        success = manager.add_source(name, base_url, priority, enabled, source_type)
        return jsonify({
            'success': success,
            'errors': [] if success else ['Failed to add source']
        })

    elif request.method == 'PUT':
        # Update an existing source
        data = request.json
        name = data.get('name')

        if not name:
            return jsonify({
                'success': False,
                'errors': ['Name is required']
            })

        # Build kwargs for update
        kwargs = {}
        if 'base_url' in data:
            kwargs['base_url'] = data['base_url']
        if 'priority' in data:
            kwargs['priority'] = data['priority']
        if 'enabled' in data:
            kwargs['enabled'] = data['enabled']
        if 'source_type' in data:
            kwargs['source_type'] = data['source_type']

        manager = titledb_sources.TitleDBSourceManager()
        success = manager.update_source(name, **kwargs)
        return jsonify({
            'success': success,
            'errors': [] if success else ['Failed to update source']
        })

    elif request.method == 'DELETE':
        # Remove a source
        data = request.json
        name = data.get('name')

        if not name:
            return jsonify({
                'success': False,
                'errors': ['Name is required']
            })

        manager = titledb_sources.TitleDBSourceManager()
        success = manager.remove_source(name)
        return jsonify({
            'success': success,
            'errors': [] if success else ['Failed to remove source']
        })