from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from flask import Response

# Metrics definitions
FILES_IDENTIFIED = Counter('myfoil_files_identified_total', 
    'Total files identified', ['app_type'])

IDENTIFICATION_DURATION = Histogram('myfoil_identification_duration_seconds',
    'Time spent identifying files')

LIBRARY_SIZE = Gauge('myfoil_library_size_bytes', 
    'Total library size in bytes')

ACTIVE_SCANS = Gauge('myfoil_active_scans', 
    'Number of active library scans')

DATABASE_QUERIES = Counter('myfoil_database_queries_total',
    'Total database queries', ['operation'])

def init_metrics(app):
    @app.route('/metrics')
    def metrics():
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    logger = app.logger
    logger.info("Prometheus metrics initialized at /metrics")
