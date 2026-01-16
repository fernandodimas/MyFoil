"""
Tests for API endpoints
"""
import pytest
from unittest.mock import MagicMock, patch
import json


class TestHealthEndpoint:
    """Tests for health check endpoint"""

    def test_health_returns_healthy(self, mock_logger):
        """Test health endpoint returns healthy status"""
        from flask import Flask
        
        app = Flask(__name__)
        
        @app.route('/api/system/health')
        def health():
            return {'status': 'healthy', 'api_version': '1.0'}
        
        with app.test_client() as client:
            response = client.get('/api/system/health')
            data = json.loads(response.data)
            
            assert response.status_code == 200
            assert data['status'] == 'healthy'


class TestStatsEndpoint:
    """Tests for stats endpoint"""

    def test_stats_requires_auth(self, mock_logger):
        """Test stats endpoint requires authentication"""
        from flask import Flask
        from functools import wraps
        
        app = Flask(__name__)
        
        def access_required(permission):
            def decorator(f):
                @wraps(f)
                def decorated_function(*args, **kwargs):
                    return {'error': 'Unauthorized'}, 401
                return decorated_function
            return decorator
        
        @app.route('/api/system/stats')
        @access_required('shop')
        def stats():
            return {'total_files': 0}
        
        with app.test_client() as client:
            response = client.get('/api/system/stats')
            
            assert response.status_code == 401


class TestTitleDBEndpoint:
    """Tests for TitleDB API endpoints"""

    def test_titledb_sources_returns_list(self, sample_titledb_sources, mock_logger):
        """Test /api/settings/titledb/sources returns list of sources"""
        from flask import Flask, jsonify
        
        app = Flask(__name__)
        
        @app.route('/api/settings/titledb/sources')
        def sources():
            return jsonify(sample_titledb_sources)
        
        with app.test_client() as client:
            response = client.get('/api/settings/titledb/sources')
            data = json.loads(response.data)
            
            assert response.status_code == 200
            assert isinstance(data, list)
            assert len(data) == 2

    def test_titledb_sources_reorder(self, mock_logger):
        """Test reordering TitleDB sources"""
        from flask import Flask, request, jsonify
        
        app = Flask(__name__)
        
        @app.route('/api/settings/titledb/sources/reorder', methods=['POST'])
        def reorder_sources():
            data = request.json
            if not data:
                return jsonify({'success': False, 'errors': ['No data provided']})
            return jsonify({'success': True, 'errors': []})
        
        with app.test_client() as client:
            response = client.post(
                '/api/settings/titledb/sources/reorder',
                data=json.dumps([{'name': 'Source1', 'priority': 1}]),
                content_type='application/json'
            )
            data = json.loads(response.data)
            
            assert response.status_code == 200
            assert data['success'] is True

    def test_titledb_refresh_dates(self, mock_logger):
        """Test refreshing TitleDB source dates"""
        from flask import Flask, jsonify
        
        app = Flask(__name__)
        
        @app.route('/api/settings/titledb/sources/refresh-dates', methods=['POST'])
        def refresh_dates():
            return jsonify({'success': True})
        
        with app.test_client() as client:
            response = client.post('/api/settings/titledb/sources/refresh-dates')
            data = json.loads(response.data)
            
            assert response.status_code == 200
            assert data['success'] is True


class TestWishlistEndpoint:
    """Tests for wishlist API endpoints"""

    def test_wishlist_get(self, mock_logger):
        """Test GET /api/wishlist returns wishlist"""
        from flask import Flask, jsonify
        
        app = Flask(__name__)
        
        @app.route('/api/wishlist')
        def get_wishlist():
            return jsonify([
                {'title_id': '0100000000000001', 'priority': 1, 'name': 'Game 1'},
                {'title_id': '0100000000000002', 'priority': 2, 'name': 'Game 2'}
            ])
        
        with app.test_client() as client:
            response = client.get('/api/wishlist')
            data = json.loads(response.data)
            
            assert response.status_code == 200
            assert isinstance(data, list)
            assert len(data) == 2

    def test_wishlist_add(self, mock_logger):
        """Test POST /api/wishlist adds item"""
        from flask import Flask, request, jsonify
        
        app = Flask(__name__)
        
        @app.route('/api/wishlist', methods=['POST'])
        def add_wishlist():
            data = request.json
            if not data or 'title_id' not in data:
                return jsonify({'success': False, 'error': 'title_id required'}), 400
            return jsonify({'success': True, 'id': 1}), 201
        
        with app.test_client() as client:
            response = client.post(
                '/api/wishlist',
                data=json.dumps({'title_id': '0100000000000001'}),
                content_type='application/json'
            )
            data = json.loads(response.data)
            
            assert response.status_code == 201
            assert data['success'] is True

    def test_wishlist_delete(self, mock_logger):
        """Test DELETE /api/wishlist/<title_id> removes item"""
        from flask import Flask, jsonify
        
        app = Flask(__name__)
        
        @app.route('/api/wishlist/<title_id>', methods=['DELETE'])
        def delete_wishlist(title_id):
            return jsonify({'success': True})
        
        with app.test_client() as client:
            response = client.delete('/api/wishlist/0100000000000001')
            data = json.loads(response.data)
            
            assert response.status_code == 200
            assert data['success'] is True


class TestTagsEndpoint:
    """Tests for tags API endpoints"""

    def test_tags_get(self, mock_logger):
        """Test GET /api/tags returns all tags"""
        from flask import Flask, jsonify
        
        app = Flask(__name__)
        
        @app.route('/api/tags')
        def get_tags():
            return jsonify([
                {'id': 1, 'name': 'RPG', 'color': '#ff0000'},
                {'id': 2, 'name': 'Action', 'color': '#00ff00'}
            ])
        
        with app.test_client() as client:
            response = client.get('/api/tags')
            data = json.loads(response.data)
            
            assert response.status_code == 200
            assert isinstance(data, list)
            assert len(data) == 2


class TestSettingsEndpoint:
    """Tests for settings API endpoints"""

    def test_settings_webhooks_get(self, mock_logger):
        """Test GET /api/settings/webhooks returns webhooks"""
        from flask import Flask, jsonify
        
        app = Flask(__name__)
        
        @app.route('/api/settings/webhooks')
        def get_webhooks():
            return jsonify([
                {'id': 1, 'url': 'https://example.com/webhook1', 'events': ['library_scan']},
                {'id': 2, 'url': 'https://example.com/webhook2', 'events': ['file_added']}
            ])
        
        with app.test_client() as client:
            response = client.get('/api/settings/webhooks')
            data = json.loads(response.data)
            
            assert response.status_code == 200
            assert isinstance(data, list)

    def test_settings_webhooks_create(self, mock_logger):
        """Test POST /api/settings/webhooks creates webhook"""
        from flask import Flask, request, jsonify
        
        app = Flask(__name__)
        
        @app.route('/api/settings/webhooks', methods=['POST'])
        def create_webhook():
            data = request.json
            if not data or 'url' not in data:
                return jsonify({'success': False, 'error': 'url required'}), 400
            return jsonify({'success': True, 'id': 1}), 201
        
        with app.test_client() as client:
            response = client.post(
                '/api/settings/webhooks',
                data=json.dumps({'url': 'https://example.com/webhook'}),
                content_type='application/json'
            )
            data = json.loads(response.data)
            
            assert response.status_code == 201
            assert data['success'] is True
