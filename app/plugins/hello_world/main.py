from plugin_system import MyFoilPlugin
import logging

logger = logging.getLogger('main')

class HelloWorldPlugin(MyFoilPlugin):
    def __init__(self, app=None):
        super().__init__(app)
        self.name = "Hello World"
        self.description = "A simple example plugin"
        self.version = "1.0.0"

    def on_load(self):
        logger.info("Hello World plugin initialized!")

    def on_library_updated(self, data):
        logger.info("Hello World: Library was updated!")

    def on_scan_complete(self, results):
        logger.info(f"Hello World: Scan complete! Found {results.get('count', 0)} files.")
