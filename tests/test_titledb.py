"""
Tests for TitleDB functionality
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch, mock_open
import json
import os


@pytest.mark.skip(reason="Requires full Flask app context and config files")
class TestTitleDBDownload:
    """Tests for TitleDB download functionality"""

    def test_download_titledb_file_success(self, sample_titledb_sources, mock_logger):
        """Test successful download of TitleDB file"""
        with patch('titledb.requests.get') as mock_get, \
             patch('builtins.open', mock_open()) as mock_file, \
             patch('titledb.logger', mock_logger):
            
            # Mock successful response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_response.iter_content = lambda chunk_size: [b'test data']
            mock_get.return_value = mock_response
            
            # Test download
            from titledb import download_titledb_file
            result = download_titledb_file('test.json', force=True)
            
            assert result is True
            mock_get.assert_called_once()

    def test_download_titledb_file_404(self, sample_titledb_sources, mock_logger):
        """Test download fails on 404"""
        with patch('titledb.requests.get') as mock_get, \
             patch('titledb.logger', mock_logger):
            
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response
            
            from titledb import download_titledb_file
            result = download_titledb_file('nonexistent.json')
            
            assert result is False

    def test_download_titledb_file_exception(self, sample_titledb_sources, mock_logger):
        """Test download handles exceptions gracefully"""
        with patch('titledb.requests.get') as mock_get, \
             patch('titledb.logger', mock_logger):
            
            mock_get.side_effect = Exception("Network error")
            
            from titledb import download_titledb_file
            result = download_titledb_file('test.json')
            
            assert result is False


@pytest.mark.skip(reason="Requires full Flask app context and config files")
@pytest.mark.skip(reason="Requires full Flask app context and config files")
class TestTitleDBUpdate:
    """Tests for TitleDB update functionality"""

    def test_check_titledb_updates_missing_files(self, mock_logger):
        """Test update check returns True when critical files are missing"""
        with patch('titledb.titles') as mock_titles, \
             patch('titledb.os.path.exists') as mock_exists, \
             patch('titledb.logger', mock_logger), \
             patch('titledb.get_source_manager') as mock_source_mgr:
            
            mock_exists.return_value = False
            mock_titles.get_titles_count.return_value = 0
            mock_source_mgr.return_value = MagicMock()
            
            from titledb import check_titledb_updates
            result = check_titledb_updates()
            
            assert result is True

    def test_check_titledb_updates_no_updates(self, mock_logger):
        """Test update check returns False when everything is up to date"""
        with patch('titledb.titles') as mock_titles, \
             patch('titledb.os.path.exists') as mock_exists, \
             patch('titledb.os.path.getsize') as mock_getsize, \
             patch('titledb.logger', mock_logger), \
             patch('titledb.get_source_manager') as mock_source_mgr:
            
            mock_exists.return_value = True
            mock_getsize.return_value = 1000000
            mock_titles.get_titles_count.return_value = 90000
            mock_titles.get_loaded_titles_file.return_value = ['test.json']
            
            mock_source = MagicMock()
            mock_source.enabled = True
            mock_source.name = 'Test Source'
            mock_source.base_url = 'https://test.com'
            mock_source.remote_date = None
            mock_source_mgr.return_value.get_active_sources.return_value = [mock_source]
            
            from titledb import check_titledb_updates
            result = check_titledb_updates()
            
            assert result is False

    def test_check_titledb_updates_force(self, mock_logger):
        """Test force update returns True regardless of state"""
        with patch('titledb.titles') as mock_titles, \
             patch('titledb.os.path.exists') as mock_exists, \
             patch('titledb.logger', mock_logger):
            
            mock_exists.return_value = True
            mock_titles.get_titles_count.return_value = 90000
            
            from titledb import check_titledb_updates
            result = check_titledb_updates(force=True)
            
            assert result is True


@pytest.mark.skip(reason="Requires full Flask app context and config files")
class TestTitleDBSources:
    """Tests for TitleDB source management"""

    def test_source_manager_load_sources(self, sample_titledb_sources, mock_logger):
        """Test source manager loads sources from config"""
        mock_config = MagicMock()
        mock_config.exists.return_value = True
        mock_config.read_text.return_value = json.dumps(sample_titledb_sources)
        
        with patch('titledb_sources.Path') as mock_path, \
             patch('titledb_sources.open', mock_open(mock_config.read_text())):
            
            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance
            mock_path_instance.exists.return_value = True
            mock_path_instance.read_text.return_value = json.dumps(sample_titledb_sources)
            
            from titledb_sources import TitleDBSourceManager
            manager = TitleDBSourceManager('/fake/path')
            
            assert len(manager.sources) == 2

    def test_source_manager_get_active_sources(self, sample_titledb_sources, mock_logger):
        """Test source manager returns only enabled sources"""
        mock_config = MagicMock()
        mock_config.exists.return_value = True
        mock_config.read_text.return_value = json.dumps(sample_titledb_sources)
        
        with patch('titledb_sources.Path') as mock_path, \
             patch('titledb_sources.open', mock_open(mock_config.read_text())):
            
            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance
            mock_path_instance.exists.return_value = True
            mock_path_instance.read_text.return_value = json.dumps(sample_titledb_sources)
            
            from titledb_sources import TitleDBSourceManager
            manager = TitleDBSourceManager('/fake/path')
            
            active_sources = manager.get_active_sources()
            
            # All sources in sample are enabled
            assert len(active_sources) == 2

    def test_source_to_dict(self, sample_titledb_sources, mock_logger):
        """Test source to_dict method returns expected format"""
        with patch('titledb_sources.Path') as mock_path:
            mock_path.return_value = MagicMock()
            
            from titledb_sources import TitleDBSource
            source = TitleDBSource.from_dict(sample_titledb_sources[0])
            source_dict = source.to_dict()
            
            assert source_dict['name'] == 'Test Source 1'
            assert source_dict['enabled'] is True
            assert source_dict['priority'] == 1
