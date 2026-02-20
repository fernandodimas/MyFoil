"""
Integration Test for Myfoil TitleDB Download
Attempts to download real files from official sources
"""
import sys
import os
import unittest
from pathlib import Path

# Add app directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app')))

from titledb_sources import TitleDBSourceManager
from constants import CONFIG_DIR, TITLEDB_DIR

class TestTitleDBIntegration(unittest.TestCase):
    def setUp(self):
        # Create a temp manager
        self.manager = TitleDBSourceManager(CONFIG_DIR)
        os.makedirs(TITLEDB_DIR, exist_ok=True)

    def test_real_download_from_github(self):
        """Test downloading versions.json from GitHub source"""
        filename = "versions.txt"
        dest_path = os.path.join(TITLEDB_DIR, "test_integration_versions.txt")
        
        print(f"\n🚀 Attempting real download of {filename}...")
        
        # Ensure blawar source is enabled for this test
        self.manager.update_source("blawar/titledb (GitHub)", enabled=True, priority=1)
        
        success, source_name, error = self.manager.download_file(filename, dest_path, timeout=15)
        
        if success:
            print(f"✅ Success! Downloaded from {source_name}")
            self.assertTrue(os.path.exists(dest_path))
            self.assertGreater(os.path.getsize(dest_path), 0)
            # Cleanup
            os.remove(dest_path)
        else:
            print(f"❌ Failed: {error}")
            self.fail(f"Download failed: {error}")

    def test_fallback_mechanism(self):
        """Test if it falls back to second source when first fails"""
        # Add a fake failing source with priority 1
        self.manager.add_source("Fake Failing Source", "https://invalid.domain.xyz/repo", priority=1)
        
        filename = "versions.txt"
        dest_path = os.path.join(TITLEDB_DIR, "test_fallback_versions.txt")
        
        print(f"\n🚀 Testing fallback mechanism...")
        
        success, source_name, error = self.manager.download_file(filename, dest_path, timeout=5)
        
        self.assertTrue(success)
        self.assertNotEqual(source_name, "Fake Failing Source")
        print(f"✅ Success! Fell back and downloaded from {source_name}")
        
        # Cleanup
        if os.path.exists(dest_path):
            os.remove(dest_path)
        self.manager.remove_source("Fake Failing Source")

if __name__ == "__main__":
    unittest.main()
