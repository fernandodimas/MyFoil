import os
import logging
from flask_socketio import SocketIO

logger = logging.getLogger('main')

_socketio_emitter = None

def get_socketio_emitter():
    """Returns an emitter function that works even in Celery workers"""
    global _socketio_emitter
    
    if _socketio_emitter is None:
        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            try:
                # Create SocketIO client with message queue for cross-process communication
                client = SocketIO(message_queue=redis_url)
                _socketio_emitter = client.emit
                logger.info(f"SocketIO emitter created successfully with message_queue: {redis_url}")
            except Exception as e:
                logger.error(f"Failed to create SocketIO emitter: {e}", exc_info=True)
                _socketio_emitter = lambda *args, **kwargs: logger.warning(f"No-op emit called: {args[0] if args else 'unknown'}")
        else:
            logger.warning("No REDIS_URL environment variable, using no-op emitter")
            _socketio_emitter = lambda *args, **kwargs: None
            
    return _socketio_emitter
