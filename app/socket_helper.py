import os
from flask_socketio import SocketIO

_socketio_emitter = None

def get_socketio_emitter():
    """Returns an emitter function that works even in Celery workers"""
    global _socketio_emitter
    
    if _socketio_emitter is None:
        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            # We don't need a full SocketIO server, just the message queue client
            # But the easiest way to get the same .emit() behavior is this:
            client = SocketIO(message_queue=redis_url)
            _socketio_emitter = client.emit
        else:
            _socketio_emitter = lambda *args, **kwargs: None
            
    return _socketio_emitter
