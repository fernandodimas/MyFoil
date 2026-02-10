from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
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

db_files_total = Gauge("myfoil_files_total", "Total number of files")
db_titles_total = Gauge("myfoil_titles_total", "Total number of titles")
db_apps_total = Gauge("myfoil_apps_total", "Total number of apps")
db_libraries_total = Gauge("myfoil_libraries_total", "Total number of libraries")
db_files_unidentified_total = Gauge("myfoil_files_unidentified_total", "Files not yet identified")
db_files_with_errors_total = Gauge("myfoil_files_with_errors_total", "Files with identification errors")

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

ACTIVE_SCANS = Gauge("myfoil_active_scans", "Number of active library scans")


class ActiveScanTracker:
    """Context manager for tracking active scans.

    Example:
        with ACTIVE_SCANS.track_inprogress():
            perform_scan()
    """

    def __enter__(self):
        ACTIVE_SCANS.inc()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        ACTIVE_SCANS.dec()
        return False


ACTIVE_SCANS.track_inprogress = ActiveScanTracker

# System Metrics
system_cpu_usage = Gauge("myfoil_system_cpu_usage_percent", "System CPU usage percentage")

system_memory_usage = Gauge("myfoil_system_memory_usage_bytes", "System memory usage in bytes")

system_disk_usage = Gauge("myfoil_system_disk_usage_bytes", "System disk usage in bytes", ["mount_point"])


def init_metrics(app):
    @app.route("/api/metrics")
    def metrics():
        update_db_metrics()
        update_library_metrics()
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


def get_metrics_export():
    """Get Prometheus metrics export for API endpoints."""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


def update_db_metrics():
    """Update database-related metrics like connection pool size."""
    try:
        from db import db, Files, Titles, Apps, Libraries

        try:
            engine = db.session.bind
            if hasattr(engine, "pool"):
                db_connection_pool_size.labels(pool="default").set(engine.pool.size())
            else:
                db_connection_pool_size.labels(pool="default").set(10)
        except Exception:
            db_connection_pool_size.labels(pool="default").set(10)

        # Basic counts
        db_files_total.set(Files.query.count())
        db_titles_total.set(Titles.query.count())
        db_apps_total.set(Apps.query.count())
        db_libraries_total.set(Libraries.query.count())

        # Identification status
        db_files_unidentified_total.set(Files.query.filter(Files.identified == False).count())
        db_files_with_errors_total.set(Files.query.filter(Files.identification_error.isnot(None)).count())
    except Exception:
        pass


def update_library_metrics():
    """Update library-related metrics (counts and coverage)."""
    try:
        from db import Titles
        from sqlalchemy import or_

        library_games_total.set(Titles.query.filter(Titles.title_id.isnot(None)).count())
        library_games_identified.set(Titles.query.filter(Titles.have_base == True).count())
        library_games_with_cover.set(
            Titles.query.filter(or_(Titles.icon_url.isnot(None), Titles.banner_url.isnot(None))).count()
        )
    except Exception:
        pass


def track_db_query(operation, phase="unknown"):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                db_query_total.labels(operation=operation, status="success").inc()
                return result
            except Exception:
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
        system_disk_usage_percent.labels(mount_point="/").set(disk.percent)

        # Calculate API error rate (errors / total requests over last 5m)
        # This will be computed in Prometheus rules using rate functions
        # For now, set to 0 if no data
        try:
            # This is a placeholder; actual calculation in Prometheus
            api_error_rate_percent.set(0.0)
        except:
            pass
    except Exception:
        pass
