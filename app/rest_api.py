from flask_restx import Api, Resource, fields
from flask import request, jsonify, redirect
from functools import wraps
import logging
from auth import access_required

logger = logging.getLogger('main')

def init_rest_api(app):
    api = Api(app, version='1.0', title='MyFoil API',
        description='Nintendo Switch Library Manager API',
        doc='/api/docs'
    )

    # Namespaces
    ns_library = api.namespace('v1/library', description='Library operations')
    ns_titledb = api.namespace('v1/titledb', description='TitleDB operations')
    ns_system = api.namespace('v1/system', description='System operations')

    # Models
    game_model = api.model('Game', {
        'id': fields.String(required=True, description='Title ID'),
        'name': fields.String(required=True, description='Game name'),
        'version': fields.String(description='Current version'),
        'latest_version_available': fields.Integer(description='Latest version available in TitleDB'),
        'size': fields.Integer(description='Total size in bytes'),
        'has_base': fields.Boolean(description='Has base game'),
        'has_latest_version': fields.Boolean(description='Is up to date'),
        'has_all_dlcs': fields.Boolean(description='Has all DLCs'),
        'status_color': fields.String(description='Status color for UI'),
        'publisher': fields.String(description='Publisher'),
        'release_date': fields.String(description='Release date'),
        'description': fields.String(description='Game description'),
        'iconUrl': fields.String(description='Icon URL'),
        'bannerUrl': fields.String(description='Banner URL'),
        'category': fields.List(fields.String, description='Categories/Genres'),
    })

    file_model = api.model('File', {
        'id': fields.Integer(description='File unique ID'),
        'filename': fields.String(description='File name'),
        'filepath': fields.String(description='Full path on disk'),
        'size': fields.Integer(description='Size in bytes'),
        'size_formatted': fields.String(description='Human readable size'),
    })

    unidentified_file_model = api.model('UnidentifiedFile', {
        'id': fields.Integer(description='File ID'),
        'filename': fields.String(description='Filename'),
        'filepath': fields.String(description='Path'),
        'size_formatted': fields.String(description='Size'),
        'error': fields.String(description='Identification error'),
    })

    source_model = api.model('TitleDBSource', {
        'name': fields.String(description='Source name'),
        'base_url': fields.String(description='Base URL or path'),
        'priority': fields.Integer(description='Priority (lower is higher)'),
        'enabled': fields.Boolean(description='Is enabled'),
        'source_type': fields.String(description='Type of source (json/folder)'),
        'last_update': fields.String(description='Last update timestamp'),
        'status': fields.String(description='Current status'),
    })

    # Namespace Library
    @ns_library.route('/games')
    class GameList(Resource):
        @ns_library.doc('list_games')
        @access_required('shop')
        @ns_library.marshal_list_with(game_model)
        def get(self):
            """List all games in library"""
            from library import generate_library
            return generate_library()

    @ns_library.route('/games/<string:title_id>')
    @ns_library.response(404, 'Game not found')
    @ns_library.param('title_id', 'The game Title ID')
    class GameInfo(Resource):
        @ns_library.doc('get_game')
        @access_required('shop')
        def get(self, title_id):
            """Get game details with updates and DLCs"""
            from app import app_info_api
            # Reuse existing logic that returns JSON
            return app_info_api(title_id)

    @ns_library.route('/scan')
    class LibraryScan(Resource):
        @ns_library.doc('start_scan')
        @access_required('admin')
        def post(self):
            """Trigger a library scan (Async if Celery enabled)"""
            from app import scan_library_api
            return scan_library_api()

    @ns_library.route('/scan/status')
    class LibraryScanStatus(Resource):
        @ns_library.doc('get_scan_status')
        @access_required('shop')
        def get(self):
            """Get current scan and update status"""
            from app import process_status_api
            return process_status_api()

    @ns_library.route('/files/<int:file_id>')
    @ns_library.response(404, 'File not found')
    class FileResource(Resource):
        @ns_library.doc('delete_file')
        @access_required('admin')
        def delete(self, file_id):
            """Delete a file from disk and database"""
            from app import delete_file_api
            return delete_file_api(file_id)

    @ns_library.route('/files/unidentified')
    class UnidentifiedFiles(Resource):
        @ns_library.doc('list_unidentified')
        @access_required('admin')
        @ns_library.marshal_list_with(unidentified_file_model)
        def get(self):
            """List all unidentified files"""
            from app import get_unidentified_files_api
            return get_unidentified_files_api().get_json()

    # Namespace TitleDB
    @ns_titledb.route('/sources')
    class SourceList(Resource):
        @ns_titledb.doc('list_sources')
        @access_required('admin')
        @ns_titledb.marshal_list_with(source_model)
        def get(self):
            """List all TitleDB sources"""
            import titledb
            return titledb.get_titledb_sources_status()

        @ns_titledb.doc('add_source')
        @access_required('admin')
        def post(self):
            """Add a new TitleDB source"""
            from app import titledb_sources_api
            return titledb_sources_api()

    @ns_titledb.route('/sources/<string:name>')
    @ns_titledb.param('name', 'The source name')
    class Source(Resource):
        @ns_titledb.doc('update_source')
        @access_required('admin')
        def put(self, name):
            """Update an existing TitleDB source"""
            from app import titledb_sources_api
            # Fake request body for direct call if needed or just use current request
            return titledb_sources_api()

        @ns_titledb.doc('delete_source')
        @access_required('admin')
        def delete(self, name):
            """Remove a TitleDB source"""
            from app import titledb_sources_api
            return titledb_sources_api()

    @ns_titledb.route('/update')
    class TitleDBUpdate(Resource):
        @ns_titledb.doc('force_update')
        @access_required('admin')
        def post(self):
            """Force TitleDB update in background"""
            from app import force_titledb_update_api
            return force_titledb_update_api()

    # Namespace System
    @ns_system.route('/stats')
    class Stats(Resource):
        @access_required('shop')
        def get(self):
            """Get general repository statistics"""
            from db import Files, Apps, Titles
            from constants import APP_TYPE_BASE, APP_TYPE_DLC, APP_TYPE_UPD
            
            return {
                'total_files': Files.query.count(),
                'total_games': Apps.query.filter_by(app_type=APP_TYPE_BASE, owned=True).count(),
                'total_dlcs': Apps.query.filter_by(app_type=APP_TYPE_DLC, owned=True).count(),
                'total_updates': Apps.query.filter_by(app_type=APP_TYPE_UPD, owned=True).count(),
                'unidentified_files': Files.query.filter(Files.app_id == None).count()
            }

    @ns_system.route('/health')
    class Health(Resource):
        def get(self):
            """Simple health check endpoint"""
            return {'status': 'healthy', 'api_version': '1.0'}
    
    return api
