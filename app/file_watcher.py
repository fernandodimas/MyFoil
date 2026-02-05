from constants import ALLOWED_EXTENSIONS
from utils import now_utc, debounce
import time
import os
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
from types import SimpleNamespace
import logging
import threading

# Retrieve main logger
logger = logging.getLogger("main")


class Watcher:
    def __init__(self, callback):
        self.directories = set()  # Use a set to store directories
        self.callback = callback
        self.event_handler = Handler(self.callback, watcher=self)
        # Use PollingObserver with faster timeout for Docker volumes
        # Default timeout is 1 second, we reduce to 0.5s for better responsiveness
        self.observer = PollingObserver(timeout=0.5)
        self.scheduler_map = {}
        logger.info("[WATCHDOG-INIT] Created PollingObserver with 0.5s timeout for Docker volume compatibility")
        
        # Health monitoring attributes
        self.last_event_time = None
        self.error_count = 0
        self.last_error = None
        self.restart_count = 0
        self.is_running = False
        self._health_check_thread = None
        self._stop_health_check = threading.Event()

    def run(self):
        """Start observer and health monitoring"""
        try:
            self.observer.start()
            self.is_running = True
            logger.info("Watchdog observer started successfully.")
            
            # Start health check thread
            self._start_health_monitoring()
        except Exception as e:
            self.is_running = False
            self.error_count += 1
            self.last_error = str(e)
            logger.error(f"Failed to start watchdog observer: {e}")
            raise

    def stop(self):
        """Stop observer and health monitoring"""
        logger.debug("Stopping watchdog observer...")
        
        # Stop health monitoring first
        self._stop_health_check.set()
        if self._health_check_thread and self._health_check_thread.is_alive():
            self._health_check_thread.join(timeout=5)
        
        # Stop observer
        try:
            self.observer.stop()
            self.observer.join(timeout=10)
            self.is_running = False
            logger.info("Watchdog observer stopped successfully.")
        except Exception as e:
            logger.error(f"Error stopping observer: {e}")

    def _start_health_monitoring(self):
        """Start background health check thread"""
        if self._health_check_thread and self._health_check_thread.is_alive():
            return
        
        self._stop_health_check.clear()
        self._health_check_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self._health_check_thread.start()
        logger.debug("Watchdog health monitoring started.")

    def _health_check_loop(self):
        """Background thread that monitors observer health and auto-restarts if needed"""
        check_interval = 30  # Check every 30 seconds
        
        while not self._stop_health_check.is_set():
            try:
                # Check if observer is alive
                if self.is_running and not self.observer.is_alive():
                    logger.error("Watchdog observer died unexpectedly! Attempting auto-restart...")
                    self._auto_restart()
                
            except Exception as e:
                logger.error(f"Error in watchdog health check: {e}")
            
            # Wait for next check (allows early exit on stop)
            self._stop_health_check.wait(timeout=check_interval)

    def _auto_restart(self):
        """Attempt to restart the observer"""
        max_retries = 3
        base_delay = 5
        
        if self.restart_count >= max_retries:
            logger.error(f"Watchdog auto-restart failed after {max_retries} attempts. Manual intervention required.")
            self.is_running = False
            self.last_error = f"Auto-restart failed after {max_retries} attempts"
            return
        
        try:
            # Stop old observer
            try:
                self.observer.stop()
                self.observer.join(timeout=5)
            except:
                pass
            
            # Create new observer
            self.observer = PollingObserver()
            
            # Re-schedule all directories
            old_scheduler_map = self.scheduler_map.copy()
            self.scheduler_map = {}
            
            for directory in list(self.directories):
                try:
                    if os.path.exists(directory):
                        task = self.observer.schedule(self.event_handler, directory, recursive=True)
                        self.scheduler_map[directory] = task
                        logger.debug(f"Re-scheduled {directory} after restart")
                except Exception as e:
                    logger.error(f"Failed to re-schedule {directory}: {e}")
            
            # Start new observer
            self.observer.start()
            self.is_running = True
            self.restart_count += 1
            
            logger.info(f"Watchdog observer auto-restarted successfully (attempt {self.restart_count}/{max_retries})")
            
        except Exception as e:
            self.restart_count += 1
            self.error_count += 1
            self.last_error = str(e)
            self.is_running = False
            logger.error(f"Failed to auto-restart watchdog (attempt {self.restart_count}/{max_retries}): {e}")
            
            # Exponential backoff before next health check tries again
            time.sleep(base_delay * (2 ** self.restart_count))

    def restart(self):
        """Manually restart the observer (for API endpoint)"""
        logger.info("Manual watchdog restart requested...")
        self.restart_count = 0  # Reset counter for manual restart
        self.stop()
        time.sleep(2)  # Brief pause
        self.run()
        return self.is_running

    def get_status(self):
        """Get current watchdog status for monitoring"""
        return {
            "running": self.is_running,
            "observer_alive": self.observer.is_alive() if self.is_running else False,
            "directories": list(self.directories),
            "last_event_time": self.last_event_time.isoformat() if self.last_event_time else None,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "restart_count": self.restart_count,
        }

    def add_directory(self, directory):
        if directory not in self.directories:
            if not os.path.exists(directory):
                logger.warning(f"Directory {directory} does not exist, not added to watchdog.")
                return False
            logger.info(f"Adding directory {directory} to watchdog.")
            try:
                task = self.observer.schedule(self.event_handler, directory, recursive=True)
                self.scheduler_map[directory] = task
                self.directories.add(directory)
                self.event_handler.add_directory(directory)
                
                
                # Diagnostic: verify observer is alive and schedule worked
                logger.debug(f"Added observer for {directory}, is_alive: {self.observer.is_alive()}")
                
                return True
            except Exception as e:
                logger.error(f"Failed to add directory {directory} to watchdog: {e}")
                self.error_count += 1
                self.last_error = str(e)
                return False
        return False

    def remove_directory(self, directory):
        logger.debug(f"Removing {directory} from watchdog monitoring...")
        if directory in self.directories:
            try:
                if directory in self.scheduler_map:
                    self.observer.unschedule(self.scheduler_map[directory])
                    del self.scheduler_map[directory]
                self.directories.remove(directory)
                logger.info(f"Removed {directory} from watchdog monitoring.")
                return True
            except Exception as e:
                logger.error(f"Error removing directory {directory}: {e}")
                self.error_count += 1
                self.last_error = str(e)
                return False
        else:
            logger.info(f"{directory} not in watchdog, nothing to do.")
        return False


class Handler(FileSystemEventHandler):
    def __init__(self, callback, stability_duration=3, watcher=None):
        self._raw_callback = callback  # Callback to invoke for stable files
        self.directories = []
        self.stability_duration = stability_duration  # Stability duration in seconds (reduced from 5 to 3)
        self.tracked_files = {}  # Tracks files being copied
        self.debounced_check_final = self._debounce(self._check_file_stability, stability_duration)
        self.watcher = watcher  # Reference to parent watcher for event tracking

    def add_directory(self, directory):
        if directory not in self.directories:
            self.directories.append(directory)

    def _debounce(self, func, wait):
        """Debounce decorator for the stability check."""

        @debounce(wait)
        def debounced():
            func()

        return debounced

    def _track_file(self, event):
        """Start or update tracking for a file."""
        if event.type == "moved":
            file_path = event.dest_path
        else:
            file_path = event.src_path
        current_size = os.path.getsize(file_path)
        if file_path not in self.tracked_files:
            event.size = current_size
            event.timestamp = time.time()
            self.tracked_files[file_path] = event
        else:
            # Only reset timer if size changed
            # This prevents infinite loops where PollingObserver fires continuous 'modified' events
            # even if the file is static (common in Docker volumes)
            if current_size != self.tracked_files[file_path].size:
                self.tracked_files[file_path].size = current_size
                self.tracked_files[file_path].timestamp = time.time()

    def _check_file_stability(self):
        """Check for stable files and invoke the callback."""
        now = time.time()
        stable_files = []

        # Check all tracked files
        for file_path, file_data in list(self.tracked_files.items()):
            if not os.path.exists(file_path):
                # If the file no longer exists, stop tracking it
                del self.tracked_files[file_path]
                continue
            current_size = os.path.getsize(file_path)
            if current_size == file_data.size and (now - file_data.timestamp) >= self.stability_duration:
                stable_files.append(file_data)
                del self.tracked_files[file_path]  # Stop tracking stable file

        # Trigger the callback for all stable files
        if stable_files:
            self._raw_callback(stable_files)

    def collect_event(self, source_event, directory):
        """Track file events and trigger the stability check."""
        if source_event.is_directory:
            return

        if not any(
            source_event.src_path.endswith(ext) or (source_event.dest_path and source_event.dest_path.endswith(ext))
            for ext in ALLOWED_EXTENSIONS
        ):
            logger.debug(f"File {source_event.src_path} doesn't match allowed extensions, skipping")
            return

        # Ignore macOS metadata files starting with ._
        filename = os.path.basename(source_event.src_path)
        if filename.startswith("._"):
            return
        if hasattr(source_event, "dest_path") and source_event.dest_path:
            dest_filename = os.path.basename(source_event.dest_path)
            if dest_filename.startswith("._"):
                return

        if self.watcher:
            from datetime import datetime
            self.watcher.last_event_time = datetime.now()

        library_event = SimpleNamespace(
            type=source_event.event_type,
            directory=directory,
            src_path=source_event.src_path,
            dest_path=source_event.dest_path,
        )

        if library_event.type == "moved" and not any(
            library_event.dest_path.endswith(ext) for ext in ALLOWED_EXTENSIONS
        ):
            library_event.type = "deleted"

        if library_event.type == "deleted":
            logger.info(f"Watchdog: File deleted - {library_event.src_path}")
            self._raw_callback([library_event])
        
        elif library_event.type == "created":
            logger.info(f"Watchdog: File created, tracking stability - {library_event.src_path}")
            # Track file on create for stability
            self._track_file(library_event)
            self.debounced_check_final()

        else:
            # Track file on create or modify
            logger.debug(f"Watchdog: Tracking file for stability ({library_event.type}) - {library_event.src_path}")
            self._track_file(library_event)
            self.debounced_check_final()

        self._check_file_stability()

    def on_any_event(self, event):
        # logger.debug(f"RAW event: {event.event_type} - {event.src_path}")
        found = False
        for directory in self.directories:
            is_src_in = event.src_path.startswith(directory)
            is_dest_in = hasattr(event, 'dest_path') and event.dest_path and event.dest_path.startswith(directory)
            
            if is_src_in or is_dest_in:
                # logger.debug(f"Event matched directory {directory}, processing...")
                self.collect_event(event, directory)
                found = True
                break
