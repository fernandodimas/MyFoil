# Celery App Configuration for MyFoil
# NOTE: Monkey patching is done in tasks.py before this module is imported

import os
import logging
import sys
from celery import Celery

# DEBUG: Force file logging immediately
data_dir = os.path.join(os.getcwd(), "data")
if not os.path.exists(data_dir):
    try:
        os.makedirs(data_dir)
    except OSError:
        pass

log_file = os.path.join(data_dir, "celery_debug.log")
log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper())
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)
logger.info("Celery App initializing...")


def make_celery(app_name=__name__):
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    celery = Celery(app_name, broker=redis_url, backend=redis_url, include=["tasks"])

    celery.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        # Redis connection resilience
        broker_transport_options={
            "socket_keepalive": True,
            "socket_connect_timeout": 5,
            "socket_timeout": 5,
            "retry_on_timeout": True,
        },
        result_backend_transport_options={
            "socket_keepalive": True,
            "socket_connect_timeout": 5,
            "socket_timeout": 5,
            "retry_on_timeout": True,
        },
        broker_connection_retry_on_startup=True,
        broker_connection_max_retries=5,
        broker_connection_retry_delay=1.0,
    )

    # Auto-flush Redis ONLY if explicitly requested via environment variable
    # This prevents accidental clearing of the task queue on every app restart
    if os.environ.get("FLUSH_REDIS_ON_STARTUP", "false").lower() == "true":
        try:
            import redis

            r = redis.from_url(redis_url)
            r.flushall()
            logger.info("Redis flushed on startup (CLEAN SLATE requested)")
        except Exception as e:
            logger.warning(f"Could not flush Redis: {e}")
    else:
        logger.debug("Skipping Redis flush (default behavior)")

    return celery


celery = make_celery("myfoil")
