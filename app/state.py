import threading

# Global state variables to avoid circular imports
scan_in_progress = False
scan_lock = threading.Lock()

is_titledb_update_running = False
titledb_update_lock = threading.Lock()

watcher = None
