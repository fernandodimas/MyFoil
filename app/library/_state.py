import threading


class _LibraryCache:
    data = None
    hash = None
    lock = threading.Lock()


LIBRARY_CACHE = _LibraryCache()
