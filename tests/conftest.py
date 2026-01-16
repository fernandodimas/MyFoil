"""
Pytest fixtures and configuration for MyFoil tests
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))


@pytest.fixture(scope='session')
def app_config():
    """Mock app configuration for tests"""
    return {
        'debug': True,
        'testing': True,
        'secret_key': 'test-secret-key'
    }


@pytest.fixture
def mock_logger():
    """Create a mock logger for testing"""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    logger.warning = MagicMock()
    logger.debug = MagicMock()
    return logger


@pytest.fixture
def sample_titles():
    """Sample titles data for testing"""
    return [
        {
            'id': '0100000000000001',
            'name': 'Test Game 1',
            'author': 'Test Author',
            'version': 1,
            'added': '2026-01-01',
            'size': 1024,
            'icon_url': None,
            'background_url': None,
            'tags': [],
            'type': 'game',
            'region': 'USA',
            'is_demo': False,
            'is_hack': False,
            'apps': []
        },
        {
            'id': '0100000000000002',
            'name': 'Test Game 2',
            'author': 'Test Author',
            'version': 2,
            'added': '2026-01-02',
            'size': 2048,
            'icon_url': None,
            'background_url': None,
            'tags': ['RPG'],
            'type': 'game',
            'region': 'EUR',
            'is_demo': False,
            'is_hack': False,
            'apps': []
        }
    ]


@pytest.fixture
def sample_files():
    """Sample files data for testing"""
    return [
        {
            'id': 1,
            'filepath': '/games/test.nsp',
            'library_id': 1,
            'title_id': '0100000000000001',
            'size': 1024,
            'sha256': 'abc123',
            'file_type': 'NSP',
            'extension': '.nsp',
            'identified': True,
            'app_id': '001'
        },
        {
            'id': 2,
            'filepath': '/games/test2.nsz',
            'library_id': 1,
            'title_id': '0100000000000002',
            'size': 2048,
            'sha256': 'def456',
            'file_type': 'NSZ',
            'extension': '.nsz',
            'identified': True,
            'app_id': '002'
        }
    ]


@pytest.fixture
def sample_titledb_sources():
    """Sample TitleDB sources for testing"""
    return [
        {
            'name': 'Test Source 1',
            'base_url': 'https://example.com/titledb',
            'enabled': True,
            'priority': 1,
            'source_type': 'json',
            'last_success': None,
            'last_error': None,
            'remote_date': None
        },
        {
            'name': 'Test Source 2',
            'base_url': 'https://test.example.com/db',
            'enabled': True,
            'priority': 2,
            'source_type': 'json',
            'last_success': '2026-01-15T10:00:00',
            'last_error': None,
            'remote_date': '2026-01-15T10:00:00'
        }
    ]
