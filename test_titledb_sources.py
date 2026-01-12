"""
Test script for Myfoil TitleDB Source Manager
Run this to verify the multi-source system is working correctly
"""
import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from titledb_sources import TitleDBSourceManager, TitleDBSource
import tempfile
import shutil

def test_source_creation():
    """Test creating and managing sources"""
    print("🧪 Testing source creation...")
    
    source = TitleDBSource(
        name="Test Source",
        base_url="https://example.com/titledb",
        priority=10,
        enabled=True
    )
    
    assert source.name == "Test Source"
    assert source.base_url == "https://example.com/titledb"
    assert source.priority == 10
    assert source.enabled == True
    
    print("✅ Source creation test passed")

def test_source_serialization():
    """Test source to/from dict conversion"""
    print("🧪 Testing source serialization...")
    
    source = TitleDBSource(
        name="Test Source",
        base_url="https://example.com/titledb",
        priority=10,
        enabled=True
    )
    
    # Convert to dict
    data = source.to_dict()
    assert data['name'] == "Test Source"
    assert data['base_url'] == "https://example.com/titledb"
    
    # Convert back from dict
    restored = TitleDBSource.from_dict(data)
    assert restored.name == source.name
    assert restored.base_url == source.base_url
    
    print("✅ Source serialization test passed")

def test_source_manager():
    """Test source manager functionality"""
    print("🧪 Testing source manager...")
    
    # Create temp directory for config
    temp_dir = tempfile.mkdtemp()
    
    try:
        manager = TitleDBSourceManager(temp_dir)
        
        # Should have default sources
        assert len(manager.sources) > 0
        print(f"   Found {len(manager.sources)} default sources")
        
        # Test adding a source
        success = manager.add_source(
            name="Test Custom Source",
            base_url="https://test.example.com",
            priority=50
        )
        assert success == True
        assert len(manager.sources) == 4  # 3 defaults + 1 custom
        
        # Test duplicate prevention
        success = manager.add_source(
            name="Test Custom Source",
            base_url="https://test.example.com",
            priority=50
        )
        assert success == False  # Should fail
        
        # Test updating a source
        success = manager.update_source(
            name="Test Custom Source",
            enabled=False,
            priority=100
        )
        assert success == True
        
        # Verify update
        source = next(s for s in manager.sources if s.name == "Test Custom Source")
        assert source.enabled == False
        assert source.priority == 100
        
        # Test removing a source
        success = manager.remove_source("Test Custom Source")
        assert success == True
        assert len(manager.sources) == 3  # Back to defaults
        
        # Test getting active sources
        active = manager.get_active_sources()
        assert all(s.enabled for s in active)
        
        # Test priority sorting
        priorities = [s.priority for s in active]
        assert priorities == sorted(priorities)
        
        print("✅ Source manager test passed")
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)

def test_file_url_generation():
    """Test URL generation for files"""
    print("🧪 Testing file URL generation...")
    
    source = TitleDBSource(
        name="Test",
        base_url="https://example.com/titledb/",  # With trailing slash
        priority=1
    )
    
    url = source.get_file_url("versions.json")
    assert url == "https://example.com/titledb/versions.json"
    
    # Test without trailing slash
    source2 = TitleDBSource(
        name="Test2",
        base_url="https://example.com/titledb",  # No trailing slash
        priority=1
    )
    
    url2 = source2.get_file_url("versions.json")
    assert url2 == "https://example.com/titledb/versions.json"
    
    print("✅ File URL generation test passed")

def test_persistence():
    """Test that sources are saved and loaded correctly"""
    print("🧪 Testing source persistence...")
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Create manager and add custom source
        manager1 = TitleDBSourceManager(temp_dir)
        manager1.add_source("Persistent Test", "https://persist.test", 25)
        
        # Create new manager instance (should load from file)
        manager2 = TitleDBSourceManager(temp_dir)
        
        # Verify the custom source was loaded
        source_names = [s.name for s in manager2.sources]
        assert "Persistent Test" in source_names
        
        source = next(s for s in manager2.sources if s.name == "Persistent Test")
        assert source.base_url == "https://persist.test"
        assert source.priority == 25
        
        print("✅ Source persistence test passed")
        
    finally:
        shutil.rmtree(temp_dir)

def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("🚀 Myfoil TitleDB Source Manager Tests")
    print("="*60 + "\n")
    
    tests = [
        test_source_creation,
        test_source_serialization,
        test_file_url_generation,
        test_source_manager,
        test_persistence,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"❌ {test.__name__} failed: {e}")
            failed += 1
        except Exception as e:
            print(f"💥 {test.__name__} crashed: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    print("="*60 + "\n")
    
    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
