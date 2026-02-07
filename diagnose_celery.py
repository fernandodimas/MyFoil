#!/usr/bin/env python3
"""
Celery Worker Diagnosis Script

This script helps diagnose issues with Celery workers and task registration.
Run this inside the worker container to check:
1. Worker connection to broker (Redis)
2. Task registration
3. Worker health
"""

import os
import sys

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 80)
print("CELERY WORKER DIAGNOSTIC")
print("=" * 80)

# 1. Check environment
print("\n[1] Environment Variables:")
print(f"REDIS_URL: {os.environ.get('REDIS_URL', 'NOT SET')}")
print(f"DATABASE_URL: {os.environ.get('DATABASE_URL', 'NOT SET')}")
print(f"CELERY_REQUIRED: {os.environ.get('CELERY_REQUIRED', 'NOT SET')}")

# 2. Test Redis connection
print("\n[2] Testing Redis connection:")
try:
    import redis

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    r = redis.from_url(redis_url)
    r.ping()
    print("✅ Redis connection successful")
    print(f"   Redis version: {r.info().get('redis_version', 'unknown')}")
except Exception as e:
    print(f"❌ Redis connection failed: {e}")
    sys.exit(1)

# 3. Test Celery broker connection
print("\n[3] Testing Celery broker connection:")
try:
    from celery import Celery

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    test_celery = Celery("test", broker=redis_url)

    # Check if broker is reachable
    inspect = test_celery.control.inspect()
    try:
        stats = inspect.stats()
        print("✅ Celery broker connection successful")
        print(f"   Active workers: {list(stats.keys()) if stats else 0}")
    except Exception as e:
        print(f"⚠️  Broker reachable but no worker yet (this is normal): {e}")
except Exception as e:
    print(f"❌ Celery broker connection failed: {e}")
    import traceback

    traceback.print_exc()

# 4. Check task registration
print("\n[4] Checking task registration:")
try:
    from celery_app import celery

    # List all registered tasks
    registered_tasks = celery.tasks.keys()
    print(f"   Total registered tasks: {len(registered_tasks)}")

    # Check for specific tasks
    important_tasks = [
        "tasks.scan_all_libraries_async",
        "tasks.scan_library_async",
        "tasks.identify_file_async",
        "tasks.fetch_metadata_for_all_games_async",
    ]

    for task_name in important_tasks:
        if task_name in registered_tasks:
            print(f"   ✅ {task_name}")
            # Try to get the task object
            task = celery.tasks.get(task_name)
            if task:
                print(f"      Task object: {task}")
        else:
            print(f"   ❌ {task_name} NOT REGISTERED")

    # Show all tasks if verbose
    if "--verbose" in sys.argv or "-v" in sys.argv:
        print("\n   All registered tasks:")
        for task_name in sorted(registered_tasks):
            print(f"      - {task_name}")

except Exception as e:
    print(f"❌ Failed to check task registration: {e}")
    import traceback

    traceback.print_exc()

# 5. Test task execution (dry run)
print("\n[5] Testing task serialization:")
try:
    from celery_app import celery
    from tasks import scan_all_libraries_async

    # Try to get task without executing
    task = celery.tasks.get("tasks.scan_all_libraries_async")
    if task:
        print("✅ Task 'tasks.scan_all_libraries_async' can be accessed")
        print(f"   Task name: {task.name}")
        print(f"   Task type: {type(task)}")
    else:
        print("❌ Task 'tasks.scan_all_libraries_async' not found")

except Exception as e:
    print(f"❌ Failed to test task: {e}")
    import traceback

    traceback.print_exc()

# 6. Check Gevent patching
print("\n[6] Gevent status:")
try:
    from gevent import monkey
    from gevent import socket as gsocket
    import socket as stdlib_socket

    if hasattr(gsocket, "socket"):
        print("✅ Gevent socket available")
        print(f"   Gevent socket class: {gsocket.socket}")
        print(f"   Stdlib socket class: {stdlib_socket.socket}")
        # Check if monkey patching was applied
        if stdlib_socket.socket == gsocket.socket:
            print("   ✅ Monkey patching applied (stdlib socket == gevent socket)")
        else:
            print("   ⚠️  Monkey patching MAY NOT be applied")
    else:
        print("⚠️  Gevent socket not available")
except ImportError:
    print("⚠️  Gevent not installed")
except Exception as e:
    print(f"❌ Error checking gevent: {e}")

print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)
print("\nIf all checks pass, the worker should be able to receive and execute tasks.")
print("If tasks are not registered, check:")
print("  1. The 'tasks.py' module is importable")
print("  2. Celery is configured with include=['tasks']")
print("  3. No syntax errors in tasks.py")
print("  4. Gevent monkey patching is compatible with Celery")
