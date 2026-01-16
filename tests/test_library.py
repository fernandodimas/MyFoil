"""
Tests for library functionality
"""
import pytest
from unittest.mock import MagicMock, patch, mock_open
import json
import os


class TestLibraryValidation:
    """Tests for library file validation"""

    def test_validate_file_valid_nsp(self, mock_logger):
        """Test validation of valid NSP file"""
        from pathlib import Path
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.nsp', delete=False) as f:
            f.write(b'test data')
            temp_path = f.name
        
        try:
            from library import validate_file
            # Should not raise exception
            validate_file(temp_path)
        finally:
            os.unlink(temp_path)

    def test_validate_file_invalid_extension(self, mock_logger):
        """Test validation fails for invalid extension"""
        from pathlib import Path
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            f.write(b'test data')
            temp_path = f.name
        
        try:
            from library import validate_file
            with pytest.raises(ValueError, match="Extensão não permitida"):
                validate_file(temp_path)
        finally:
            os.unlink(temp_path)

    def test_validate_file_not_found(self, mock_logger):
        """Test validation fails for non-existent file"""
        from library import validate_file
        with pytest.raises(FileNotFoundError):
            validate_file('/nonexistent/path/file.nsp')

    def test_validate_file_empty(self, mock_logger):
        """Test validation fails for empty file"""
        from pathlib import Path
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.nsp', delete=False) as f:
            f.write(b'')
            temp_path = f.name
        
        try:
            from library import validate_file
            with pytest.raises(ValueError, match="Arquivo vazio"):
                validate_file(temp_path)
        finally:
            os.unlink(temp_path)


class TestLibraryCache:
    """Tests for library caching functionality"""

    def test_compute_apps_hash(self, sample_files, mock_logger):
        """Test apps hash computation"""
        with patch('library.os.walk') as mock_walk, \
             patch('library.hashlib.sha256') as mock_sha256, \
             patch('library.logger', mock_logger):
            
            mock_walk.return_value = [
                ('/games', [], ['test1.nsp', 'test2.nsz'])
            ]
            
            mock_hash = MagicMock()
            mock_hash.hexdigest.return_value = 'abc123'
            mock_sha256.return_value = mock_hash
            
            from library import compute_apps_hash
            result = compute_apps_hash()
            
            assert mock_sha256.called

    def test_save_and_load_library_to_disk(self, sample_titles, mock_logger):
        """Test library save and load from disk"""
        import tempfile
        import json
        
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = os.path.join(tmpdir, 'library.json')
            
            # Mock the cache file path
            with patch('library.LIBRARY_CACHE_FILE', cache_file), \
                 patch('library.logger', mock_logger):
                
                from library import save_library_to_disk, load_library_from_disk
                
                # Test save
                save_library_to_disk({
                    'hash': 'test123',
                    'library': sample_titles
                })
                
                assert os.path.exists(cache_file)
                
                # Test load
                loaded = load_library_from_disk()
                
                assert loaded is not None
                assert loaded['hash'] == 'test123'
                assert len(loaded['library']) == 2


class TestLibraryGeneration:
    """Tests for library generation"""

    def test_generate_library_returns_list(self, sample_titles, mock_logger):
        """Test generate_library returns a list"""
        with patch('library.get_libraries') as mock_get_libs, \
             patch('library.logger', mock_logger):
            
            mock_lib = MagicMock()
            mock_lib.path = '/games'
            mock_get_libs.return_value = [mock_lib]
            
            # Mock file operations
            with patch('library.os.walk') as mock_walk, \
                 patch('library.validate_file') as mock_validate:
                
                mock_walk.return_value = []
                mock_validate.return_value = None
                
                from library import generate_library
                result = generate_library()
                
                assert isinstance(result, list)


class TestAllowedExtensions:
    """Tests for allowed file extensions"""

    def test_nsp_extension_allowed(self, mock_logger):
        """Test .nsp is allowed"""
        from library import ALLOWED_EXTENSIONS
        assert '.nsp' in ALLOWED_EXTENSIONS

    def test_nsz_extension_allowed(self, mock_logger):
        """Test .nsz is allowed"""
        from library import ALLOWED_EXTENSIONS
        assert '.nsz' in ALLOWED_EXTENSIONS

    def test_xci_extension_allowed(self, mock_logger):
        """Test .xci is allowed"""
        from library import ALLOWED_EXTENSIONS
        assert '.xci' in ALLOWED_EXTENSIONS

    def test_xcz_extension_allowed(self, mock_logger):
        """Test .xcz is allowed"""
        from library import ALLOWED_EXTENSIONS
        assert '.xcz' in ALLOWED_EXTENSIONS

    def test_txt_extension_not_allowed(self, mock_logger):
        """Test .txt is not allowed"""
        from library import ALLOWED_EXTENSIONS
        assert '.txt' not in ALLOWED_EXTENSIONS
