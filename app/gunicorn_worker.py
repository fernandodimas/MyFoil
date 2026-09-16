"""
Custom gevent worker for gunicorn that patches everything EXCEPT sockets.

gevent's default monkey.patch_all() patches Python's socket module with
cooperative green sockets. But psycopg2 uses C-level libpq which has its
own socket implementation that bypasses Python's socket module. This causes:

1. libpq sends data over a real OS socket
2. gevent's event loop doesn't know about this socket
3. gevent switches greenlets mid-read, corrupting the response buffer
4. Result: 'PGRES_TUPLES_OK and no message from the libpq' errors

Strategy: Override init_process to patch with socket=False BEFORE the
parent GeventWorker patches with sockets=True.
"""

from gevent import monkey

# Patch BEFORE importing GeventWorker so our socket=False takes precedence
monkey.patch_all(socket=False)

from gunicorn.workers.ggevent import GeventWorker  # noqa: E402


class SocketSafeGeventWorker(GeventWorker):
    """Gevent worker that prevents socket patching to protect psycopg2."""

    def init_process(self):
        # CRITICAL: Patch with socket=False BEFORE super().init_process()
        # The parent's init_process() calls monkey.patch_all() which would
        # re-patch sockets. By patching first with socket=False, we ensure
        # sockets are marked as "already patched" and won't be re-patched.
        monkey.patch_all(socket=False)
        super().init_process()
