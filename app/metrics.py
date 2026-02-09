from prometheus_client import Counter, Histogram, Gauge, Summary, generate_latest, CONTENT_TYPE_LATEST
from flask import Response, request
import time
from functools import wraps

try:
    import psutil

    psutil_available = True
except ImportError:
    psutil_available = False

# Database Metrics
db_connection_pool_size = Gauge("myfoil_db_connections_active", "Number of active database connections", ["pool"])

db_query_duration_seconds = Histogram(
    "myfoil_db_query_duration_seconds", "Database query duration", ["operation", "phase"]
)

db_query_total = Counter("myfoil_db_queries_total", "Total database queries", ["operation", "status"])

# Library Metrics
library_games_total = Gauge("myfoil_library_games_total", "Total number of games in library")

library_games_identified = Gauge("myfoil_library_games_identified", "Number of identified games")

library_games_with_cover = Gauge("myfoil_library_games_with_cover", "Number of games with cover image")

library_size_bytes = Gauge("myfoil_library_size_bytes", "Total library size in bytes")

# API Metrics
api_request_duration_seconds = Histogram(
    "myfoil_api_request_duration_seconds", "API request duration", ["endpoint", "method"]
)

api_requests_total = Counter("myfoil_api_requests_total", "Total API requests", ["endpoint", "method", "status_code"])

# Identification Metrics
files_identified_total = Counter("myfoil_files_identified_total", "Total files identified", ["app_type", "status"])

identification_duration_seconds = Histogram(
    "myfoil_identification_duration_seconds", "Time spent identifying files", ["app_type"]
)

# Celery/Background Metrics
celery_queue_length = Gauge("myfoil_celery_queue_length", "Number of tasks in Celery queue", ["queue"])

celery_active_tasks = Gauge("myfoil_celery_active_tasks", "Number of active Celery tasks")

# System Metrics
system_cpu_usage = Gauge("myfoil_system_cpu_usage_percent", "System CPU usage percentage")

system_memory_usage = Gauge("myfoil_system_memory_usage_bytes", "System memory usage in bytes")

system_disk_usage = Gauge("myfoil_system_disk_usage_bytes", "System disk usage in bytes", ["mount_point"])


def init_metrics(app):
    @app.route("/api/metrics")
    def metrics():
        update_system_metrics()
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    @app.before_request
    def before_request():
        request.start_time = time.time()

    @app.after_request
    def after_request(response):
        duration = time.time() - getattr(request, "start_time", time.time())
        api_request_duration_seconds.labels(endpoint=request.endpoint or "unknown", method=request.method).observe(
            duration
        )
        api_requests_total.labels(
            endpoint=request.endpoint or "unknown", method=request.method, status_code=response.status_code
        ).inc()
        return response

    logger = app.logger
    logger.info("Prometheus metrics initialized at /api/metrics")
    logger.info("System metrics collection enabled")


def track_db_query(operation, phase="unknown"):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                db_query_total.labels(operation=operation, status="success").inc()
                return result
            except Exception as e:
                db_query_total.labels(operation=operation, status="error").inc()
                raise
            finally:
                duration = time.time() - start_time
                db_query_duration_seconds.labels(operation=operation, phase=phase).observe(duration)

        return wrapper

    return decorator


def update_system_metrics():
    if not psutil_available:
        return
    try:
        system_cpu_usage.set(psutil.cpu_percent())

        mem = psutil.virtual_memory()
        system_memory_usage.set(mem.used)

        disk = psutil.disk_usage("/")
        system_disk_usage.labels(mount_point="/").set(disk.used)
    except Exception as e:
        pass
