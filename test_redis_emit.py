#!/usr/bin/env python3
"""
Direct Redis SocketIO Test
Tests if worker can emit events that app receives via Redis pub/sub
"""
import os
import sys

# Set REDIS_URL if not already set (for local testing)
if not os.environ.get("REDIS_URL"):
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"

from flask_socketio import SocketIO
import time

def test_emit():
    redis_url = os.environ.get("REDIS_URL")
    print(f"Testing SocketIO emit to Redis: {redis_url}")
    
    try:
        # Create client (simulating worker)
        client = SocketIO(message_queue=redis_url)
        print("✅ SocketIO client created")
        
        # Emit test event
        test_data = {
            "test": True,
            "timestamp": time.time(),
            "message": "Hello from test script"
        }
        
        print(f"📤 Emitting 'test_event' with broadcast=True, namespace='/'...")
        client.emit('test_event', test_data, broadcast=True, namespace='/')
        print("✅ Emit completed without errors")
        
        print("\nNow check your app logs for this event!")
        print("If you see it, the pub/sub is working.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_emit()
