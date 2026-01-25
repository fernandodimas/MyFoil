import os
import importlib.util
import logging
from typing import List, Dict, Any

logger = logging.getLogger('main')

class MyFoilPlugin:
    """Base class for all MyFoil plugins"""
    def __init__(self, app=None):
        self.app = app
        self.name = "Base Plugin"
        self.description = "Base plugin description"
        self.version = "1.0.0"

    def on_load(self):
        """Called when plugin is loaded"""
        pass

    def on_library_updated(self, data: Dict[str, Any]):
        """Called when the library is updated"""
        pass

    def on_scan_complete(self, results: Dict[str, Any]):
        """Called when a library scan is complete"""
        pass

class PluginManager:
    """Manages MyFoil plugins"""
    def __init__(self, plugins_dir: str, app=None):
        self.plugins_dir = plugins_dir
        self.app = app
        self.plugins: List[MyFoilPlugin] = []
        self.discovered_plugins: List[Dict[str, Any]] = [] # For UI/Management
        
        if not os.path.exists(self.plugins_dir):
            os.makedirs(self.plugins_dir)

    def load_plugins(self, disabled_ids: List[str] = None):
        """Load all plugins from the plugins directory, respecting disabled list"""
        self.plugins = []
        self.discovered_plugins = []
        disabled_ids = disabled_ids or []
        
        if not os.path.exists(self.plugins_dir):
            return

        for item in os.listdir(self.plugins_dir):
            item_path = os.path.join(self.plugins_dir, item)
            if os.path.isdir(item_path):
                # Try to load main.py in the directory
                plugin_file = os.path.join(item_path, 'main.py')
                if os.path.exists(plugin_file):
                    try:
                        spec = importlib.util.spec_from_file_location(f"plugin_{item}", plugin_file)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        # Find classes that inherit from MyFoilPlugin
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if isinstance(attr, type) and issubclass(attr, MyFoilPlugin) and attr != MyFoilPlugin:
                                plugin_instance = attr(self.app)
                                plugin_instance.id = item # Directory name as ID
                                
                                is_enabled = item not in disabled_ids
                                
                                # Add to discovered list for UI
                                self.discovered_plugins.append({
                                    'id': item,
                                    'name': plugin_instance.name,
                                    'version': plugin_instance.version,
                                    'description': plugin_instance.description,
                                    'enabled': is_enabled
                                })

                                if is_enabled:
                                    plugin_instance.on_load()
                                    self.plugins.append(plugin_instance)
                                    logger.info(f"Loaded plugin: {plugin_instance.name} v{plugin_instance.version}")
                                else:
                                    logger.info(f"Plugin {item} is disabled, skipping load.")
                                
                                break # Only one plugin class per main.py supported for now
                    except Exception as e:
                        logger.error(f"Failed to load plugin {item}: {e}")

    def trigger_event(self, event_name: str, *args, **kwargs):
        """Trigger an event across all loaded plugins"""
        method_name = f"on_{event_name}"
        for plugin in self.plugins:
            if hasattr(plugin, method_name):
                try:
                    method = getattr(plugin, method_name)
                    method(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error in plugin {plugin.name} during event {event_name}: {e}")

# singleton-like access
_plugin_manager = None

def get_plugin_manager(plugins_dir=None, app=None):
    global _plugin_manager
    if _plugin_manager is None and plugins_dir:
        _plugin_manager = PluginManager(plugins_dir, app)
    return _plugin_manager
