#!/usr/bin/env python3
"""
Test Celery Task Submission

This script simulates sending a task to Celery and tracks its execution.
Use this to test if Celery workers are receiving and executing tasks correctly.
"""

import os
import sys
import time

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

print("Testing Celery Task Submission...")
print("=" * 80)

# 1. Check environment
print("\nStep 1: Checking environment...")
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
print(f"REDIS_URL: {redis_url}")

# 2. Test Redis connection
print("\nStep 2: Testing Redis connection...")
try:
    import redis

    r = redis.from_url(redis_url)
    r.ping()
    print("✅ Redis is reachable")
except Exception as e:
    print(f"❌ Redis connection failed: {e}")
    sys.exit(1)

# 3. Import Celery app
print("\nStep 3: Importing Celery app...")
try:
    from celery_app import celery

    print("✅ Celery app imported")
except Exception as e:
    print(f"❌ Failed to import Celery: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# 4. Check worker connection
print("\nStep 4: Checking Celery workers...")
try:
    inspect = celery.control.inspect()
    stats = inspect.stats()

    if stats:
        print(f"✅ Found {len(stats)} active worker(s):")
        for worker_name, worker_stats in stats.items():
            print(f"   - {worker_name}")
            for key, value in list(worker_stats.items())[:3]:
                print(f"      {key}: {value}")
    else:
        print("⚠️  No active workers found (tasks will be queued)")
except Exception as e:
    print(f"⚠️  Could not check workers: {e}")

# 5. Check task registration
print("\nStep 5: Checking task registration...")
tasks = celery.tasks.keys()
print(f"Total registered tasks: {len(tasks)}")

important_tasks = [
    "tasks.scan_all_libraries_async",
    "tasks.scan_library_async",
]

for task_name in important_tasks:
    status = "✅" if task_name in tasks else "❌"
    print(f"   {status} {task_name}")

# 6. Send a test task
print("\nStep 6: Sending test task...")
try:
    from tasks import scan_all_libraries_async

    result = scan_all_libraries_async.apply_async()
    print(f"✅ Task sent successfully!")
    print(f"   Task ID: {result.id}")
    print(f"   Task state: {result.state}")

    # Wait a bit and check result
    print("\nStep 7: Waiting for task execution (watching for 10 seconds)...")
    start_time = time.time()
    while time.time() - start_time < 10:
        state = result.state
        if state in ["SUCCESS", "FAILURE", "REVOKED"]:
            print(f"   Task completed! State: {state}")

            if state == "SUCCESS":
                print(f"   Result: {result.result}")
            elif state == "FAILURE":
                print(f"   Exception: {result.info}")
            break
        else:
            print(f"   Current state: {state}")
            time.sleep(1)
    else:
        print(f"   Task is still running after 10 seconds")
        print(f"   Current state: {result.state}")

        # Check if task is in the queue
        inspect = celery.control.inspect()
        queued = inspect.reserved()
        if queued:
            print(f"   Task is in queue:")
            for worker, tasks_ in queued.items():
                if tasks_:
                    print(f"      {worker}: {len(tasks_)} tasks")

except Exception as e:
    print(f"❌ Failed to send task: {e}")
    import traceback

    traceback.print_exc()

print("\n" + "=" * 80)
print("Test Complete")
print("=" * 80)
