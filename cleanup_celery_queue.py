#!/usr/bin/env python3
"""
Script to purge stale Celery tasks from Redis queue.
This prevents duplicate task executions by clearing pending tasks.
"""

import sys
import os
from datetime import timedelta

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from app import create_app


def main():
    """Purge all pending Celery tasks from Redis"""
    print("=" * 80)
    print("Celery Task Queue Cleanup")
    print("=" * 80)

    app = create_app()

    with app.app_context():
        try:
            # Check if Redis is configured
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            print(f"\nRedis URL: {redis_url}")

            # Check if Celery is enabled
            celery_enabled = os.environ.get("CELERY_ENABLED", "").lower() == "true"
            print(f"Celery Enabled: {celery_enabled}")

            if not celery_enabled:
                print("\n⚠️ Celery is not enabled. Skipping queue cleanup.")
                return

            # Inspect Celery queue
            from celery_app import celery

            print("\nInspecting Celery queue...")
            inspect = celery.control.inspect()

            # Active tasks
            active = inspect.active()
            if active:
                total_active = sum(len(tasks) for tasks in active.values())
                print(f"Active tasks: {total_active}")
            else:
                print("Active tasks: 0")

            # Reserved tasks
            reserved = inspect.reserved()
            if reserved:
                total_reserved = sum(len(tasks) for tasks in reserved.values())
                print(f"Reserved tasks: {total_reserved}")
            else:
                print("Reserved tasks: 0")

            # Scheduled tasks
            scheduled = inspect.scheduled()
            if scheduled:
                total_scheduled = sum(len(tasks) for tasks in scheduled.values())
                print(f"Scheduled tasks: {total_scheduled}")
            else:
                print("Scheduled tasks: 0")

            # Option to purge
            print("\n" + "=" * 80)
            print("Options:")
            print("1. Show all pending tasks (reserved + scheduled)")
            print("2. Purge all pending tasks from queue")
            print("3. Exit without changes")
            print("=" * 80)

            choice = input("\nSelect option (1/2/3): ").strip()

            if choice == "1":
                # Show all pending tasks
                print("\n--- Reserved Tasks ---")
                if reserved:
                    for worker, tasks in reserved.items():
                        print(f"\nWorker: {worker}")
                        for task in tasks:
                            print(f"  - {task.get('name', 'Unknown')} (ID: {task.get('id', 'N/A')})")
                else:
                    print("No reserved tasks")

                print("\n--- Scheduled Tasks ---")
                if scheduled:
                    for worker, tasks in scheduled.items():
                        print(f"\nWorker: {worker}")
                        for task in tasks:
                            eta = task.get("eta", "N/A")
                            print(f"  - {task.get('name', 'Unknown')} (ID: {task.get('id', 'N/A')}, ETA: {eta})")
                else:
                    print("No scheduled tasks")

            elif choice == "2":
                # Purge pending tasks
                confirm = input("\n⚠️ This will remove ALL pending tasks. Confirm? (yes/no): ").strip().lower()
                if confirm == "yes":
                    from celery import current_app as celery_current_app

                    # Purge all tasks
                    purged = celery_current_app.control.purge()
                    print(f"\n✓ Purged {purged} tasks from queue")
                    print("\nRemaining tasks:")
                    print(
                        "  Active:", sum(len(tasks) for tasks in inspect.active().values()) if inspect.active() else 0
                    )
                    print(
                        "  Reserved:",
                        sum(len(tasks) for tasks in inspect.reserved().values()) if inspect.reserved() else 0,
                    )
                    print(
                        "  Scheduled:",
                        sum(len(tasks) for tasks in inspect.scheduled().values()) if inspect.scheduled() else 0,
                    )
                else:
                    print("\n✗ Cancelled purge operation")

            else:
                print("\nExiting without changes")

        except Exception as e:
            print(f"\n✗ Error during queue cleanup: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
