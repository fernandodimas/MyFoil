import os
import logging
from flask_socketio import SocketIO

logger = logging.getLogger('main')

_socketio_emitter = None

def get_socketio_emitter():
    """Returns an emitter function that works even in Celery workers"""
    global _socketio_emitter
    
    # If already have a valid emitter, return it
    if _socketio_emitter is not None:
        # Check if it's a no-op emitter from a previous failed attempt
        # If it is, we might want to try again
        if hasattr(_socketio_emitter, '__name__') and _socketio_emitter.__name__ == '<lambda>':
             logger.debug("Previous emitter was a no-op, attempting to recreate...")
        else:
             return _socketio_emitter
    
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            # Create SocketIO client with message queue for cross-process communication
            # Use short timeouts to avoid hanging the task if Redis is briefly down
            client = SocketIO(message_queue=redis_url, socketio_path='socket.io')
            
            def broadcast_emit(event, data, *args, **kwargs):
                """Wrapper that ensures broadcast=True for worker->web communication"""
                # Force broadcast and ensure we're not using namespaces unless specified
                kwargs['broadcast'] = True
                try:
                    client.emit(event, data, *args, **kwargs)
                    logger.debug(f"SocketIO: Worker successfully emitted '{event}' (broadcast=True)")
                except Exception as e:
                    logger.error(f"SocketIO: Worker emit failed for '{event}': {e}")
            
            _socketio_emitter = broadcast_emit
            logger.info(f"SocketIO: Broadcast emitter created successfully (Redis: {redis_url})")
        except Exception as e:
            logger.error(f"SocketIO: Failed to create emitter: {e}")
            # Don't cache the no-op permanently so we can retry next time
            return lambda *args, **kwargs: logger.warning(f"SocketIO: No-op emit called for '{args[0] if args else 'unknown'}' (Redis unreachable)")
    else:
        logger.warning("SocketIO: No REDIS_URL environment variable, using no-op emitter")
        _socketio_emitter = lambda *args, **kwargs: None
            
    return _socketio_emitter
