import os
import logging
from flask_socketio import SocketIO

logger = logging.getLogger('main')

_socketio_emitter = None

def get_socketio_emitter():
    """Returns an emitter function that works even in Celery workers"""
    import sys
    global _socketio_emitter
    
    pid = os.getpid()
    
    # If already have a valid emitter, return it
    if _socketio_emitter is not None:
        # Check if it's a no-op emitter from a previous failed attempt
        # If it is, we might want to try again
        if hasattr(_socketio_emitter, '__name__') and _socketio_emitter.__name__ == '<lambda>':
             logger.debug(f"[SocketIO PID:{pid}] Previous emitter was a no-op, attempting to recreate...")
        else:
             logger.debug(f"[SocketIO PID:{pid}] Returning existing emitter")
             return _socketio_emitter
    
    redis_url = os.environ.get("REDIS_URL")
    logger.info(f"[SocketIO PID:{pid}] Creating new emitter with REDIS_URL={redis_url}")
    
    if redis_url:
        try:
            # Create SocketIO client with message queue for cross-process communication
            # Use short timeouts to avoid hanging the task if Redis is briefly down
            logger.info(f"[SocketIO PID:{pid}] Initializing SocketIO client...")
            client = SocketIO(message_queue=redis_url, socketio_path='socket.io')
            
            def broadcast_emit(event, data, *args, **kwargs):
                """Wrapper that ensures broadcast=True for worker->web communication"""
                # Force broadcast and ensure we're using the default namespace
                kwargs['broadcast'] = True
                kwargs['namespace'] = '/'  # EXPLICIT namespace
                
                import sys
                pid = os.getpid()
                logger.info(f"[SocketIO PID:{pid}] 📤 Emitting event '{event}' with broadcast=True, namespace='/', data={type(data).__name__}")
                
                try:
                    client.emit(event, data, *args, **kwargs)
                    logger.info(f"[SocketIO PID:{pid}] ✅ Successfully emitted '{event}' (broadcast=True, namespace='/')")
                except Exception as e:
                    logger.error(f"[SocketIO PID:{pid}] ❌ Emit failed for '{event}': {e}", exc_info=True)
            
            _socketio_emitter = broadcast_emit
            logger.info(f"[SocketIO PID:{pid}] ✅ Broadcast emitter created successfully (Redis: {redis_url})")
        except Exception as e:
            logger.error(f"[SocketIO PID:{pid}] ❌ Failed to create SocketIO emitter: {e}", exc_info=True)
            # Don't cache the no-op permanently so we can retry next time
            return lambda *args, **kwargs: logger.warning(f"[SocketIO PID:{pid}] No-op emit called for '{args[0] if args else 'unknown'}' (Redis unreachable)")
    else:
        logger.warning(f"[SocketIO PID:{pid}] ⚠️ No REDIS_URL environment variable, using no-op emitter")
        _socketio_emitter = lambda *args, **kwargs: None
            
    return _socketio_emitter
