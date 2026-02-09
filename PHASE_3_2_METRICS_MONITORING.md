# Phase 3.2: Metrics & Monitoring Implementation

## 📊 What Was Implemented

1. **Prometheus Metrics System** (`app/metrics.py`)
2. **Metrics Endpoint** (`/api/metrics` on system_bp)
3. **Health Check Endpoint** (`/api/health`)
4. **Grafana Dashboard** (`grafana_dashboard.json`)

---

## 🎯 Metrics Available

### Application Metrics
- `myfoil_app_info` - App version and build info
- `myfoil_version_info` - Current version label

### Database Metrics
- `myfoil_files_total` - Total number of files
- `myfoil_titles_total` - Total number of titles
- `myfoil_apps_total` - Total number of apps
- `myfoil_libraries_total` - Total number of libraries
- `myfoil_files_identified_total` - Successfully identified files
- `myfoil_files_unidentified_total` - Files not yet identified
- `myfoil_files_with_errors_total` - Files with identification errors
- `myfoil_db_query_duration_seconds` - Database query duration histogram
- `myfoil_db_query_errors_total` - Database query error counter

### Library Performance Metrics
- `myfoil_library_load_duration_seconds` - Library load time histogram
- `myfoil_library_generation_duration_seconds` - Library generation time histogram
- `myfoil_library_cache_size_bytes` - Cache size in bytes
- `myfoil_library_cache_hits_total` - Cache hit counter
- `myfoil_library_cache_misses_total` - Cache miss counter

### File Identification Metrics
- `myfoil_identification_duration_seconds` - File identification time histogram
- `myfoil_identification_tasks_total` - Task counter (success/failed)
- `myfoil_identification_in_progress` - Active identification count

### API Request Metrics
- `myfoil_api_request_duration_seconds` - API response time histogram
- `myfoil_api_request_errors_total` - API error counter

### Celery Metrics
- `myfoil_celery_tasks_total` - Task counter by status
- `myfoil_celery_task_duration_seconds` - Task duration histogram

### System Metrics
- `myfoil_system_disk_total_bytes` - Total disk space per library
- `myfoil_system_disk_free_bytes` - Free disk space per library
- `myfoil_system_disk_used_bytes` - Used disk space per library
- `myfoil_requests_in_progress` - Active request count
- `myfoil_identification_in_progress` - Active files being identified

---

## 🔗 Endpoints

### Prometheus Metrics
**Endpoint:** `GET /api/metrics`
**Authentication:** Admin access required
**Purpose:** Export metrics in Prometheus format for monitoring

**Example Request:**
```bash
curl -H "Authorization: Basic YWRtaW46cGFzc3dvcmQ=" \
  http://localhost:8465/api/metrics
```

**Example Response:**
```
# HELP
# TYPE myfoil_files_identified_total gauge
myfoil_files_identified_total 512

# HELP
# TYPE myfoil_files_total gauge
myfoil_files_total 542

# HELP
# TYPE myfoil_identification_tasks_total counter
myfoil_identification_tasks_total{status="success"} 512
...
```

---

### Health Check
**Endpoint:** `GET /api/health`
**Authentication:** None (public)
**Purpose:** Health status for monitoring/alerting

**Example Request:**
```bash
curl http://localhost:8465/api/health
```

**Example Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-02-09T17:20:00Z",
  "database": "connected",
  "cache": "working",
  "metrics": "enabled",
  "celery": "disabled"
}
```

**Status Codes:**
- **200**: All systems healthy
- **503**: One or more systems degraded

---

## 📊 Grafana Dashboard

### File: `grafana_dashboard.json`

**How to Import:**

1. **Access Grafana:**
   - Navigate to Grafana
   - Go to "+" → "Import dashboard"

2. **Upload Dashboard:**
   - Select "Upload JSON file"
   - Upload `grafana_dashboard.json`

3. **Configure Datasource:**
   - Edit dashboard settings
   - Add Prometheus datasource named `myfoil_prometheus`
   - URL: `http://host.docker.internal:9090/metrics` (if using Docker)
   - OR `http://localhost:8465/api/metrics` (local development)

4. **Metrics Available:**
   - Library Overview - Counters for files, titles, apps
   - File Status - Table view of identified/unidentified/error files
   - Identification Tasks - Success/failure rates and totals
   - Library Load Performance - Median, 95th percentile, average
   - Disk Usage - Total, free, used (per library)
   - API Performance - Response times and error rates

**Refresh Rate:** 30 seconds (all panels)
**Timezone:** UTC

**Panels Summary:**

| Panel | Type | Metrics |
|-------|------|---------|
| Library Overview | Stat | Total files, titles, apps |
| File Status | Table | Identified, unidentified, error counts |
| Identification Tasks | Timeseries | Task rates, success/failure |
| Library Load Performance | Timeseries | Load time percentiles |
| Disk Usage | Timeseries | Total, free, used GB counts |
| API Performance | Timeseries | Response time and error rates |

---

## 🚀 Usage Examples

### Using Prometheus

```bash
# Create alert for high error rate
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PrometheusRule
spec:
  groups:
  - name: myfoil_alerts
    rules:
      - alert: HighIdentificationErrorRate
        expr: |
          rate(myfoil_identification_tasks_total{status="failed"}[5m]) > 0.1
        for: 10m
        labels:
          severity: warning
          component: identification
        annotations:
          description: "More than 10% of identifications are failing"
        annotations:
          summary: "High identification error rate detected"
EOF
```

### Alerts Recommended

1. **Database Slow Queries**
   ```yaml
   alert: SlowDatabaseQueries
   expr: rate(myfoil_db_query_duration_seconds_sum{model="Files",operation="SELECT"}[5m]) / rate(myfoil_db_query_duration_seconds_count{model="Files",operation="SELECT"}[5m]) > 1
   for: 5m
   ```

2. **Low Disk Space**
   ```yaml
   alert: LowDiskSpace
   expr: myfoil_system_disk_free_bytes{library_path="/externo"} / myfoil_system_disk_total_bytes{library_path="/externo"} < 0.1
   for: 10m
   ```

3. **API Error Rate**
   ```yaml
   alert: HighAPIErrorRate
   expr: rate(myfoil_api_request_errors_total{endpoint!~"/health|/metrics"}[5m]) > 0.05
   for: 5m
   ```

---

## 🔧 Integration Instructions

### For Docker Compose

**1. Update docker-compose.yml:**

```yaml
services:
  myfoil:
    image: ghcr.io/fernandodimas/myfoil:latest
    environment:
      # Enable metrics endpoint access (if needed for external monitoring)
      - MYFOIL_METRICS_ENABLED=true
    ports:
      - "8465:8465"
    volumes:
      - ./data:/app/data
    labels:
      - "prometheus.io/scrape: true"
      - "prometheus.io/port: 8465"
      - "prometheus.io/path: /api/metrics"

  prometheus:
    image: prom/prometheus:v2.45.0
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--web.console.templates=/etc/prometheus/consoles'
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    depends_on:
      - myfoil

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - ./grafana_data:/var/lib/grafana
      - ./grafana_dashboard.json:/etc/grafana/provisioning/dashboards/
    depends_on:
      - myfoil
```

**2. Create prometheus.yml:**

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'myfoil'
    metrics_path: '/api/metrics'
    scrape_interval: 30s
    static_configs:
      - targets:
        - 'host.docker.internal:8465'
    basic_auth:
      username: 'admin'  # Change if needed
      password: 'your_password'  # Change if needed
```

### For Monitoring Stack

**Option 1: Use Prometheus + Grafana (Full Stack)**
- Complete metrics collection and visualization
- Powerful alerting and dashboards
- Recommended for production

**Option 2: Use Only Prometheus Endpoint**
- Collect metrics with existing monitoring tools
- Export metrics to external monitoring service
- Lightweight solution

**Option 3: Use Cloud Metrics**
- Export to Datadog, New Relic, or similar
- Works with `/api/metrics` endpoint
- No infrastructure to maintain

---

## 📈 Using Metrics in Application Code

### Tracking Library Load Time

```python
from app.metrics import update_library_metrics
import time

@app.route("/api/library")
def library_api():
    start_time = time.time()
    
    # Load library...
    data = generate_library(force=False)
    
    duration = time.time() - start_time
    update_library_metrics(load_duration=duration)
    
    return jsonify(data)
```

### Tracking Database Queries

```python
from app.metrics import track_database_query

with app.app_context():
    start = time.time()
    try:
        files = Files.query.all()
        duration = time.time() - start
        track_database_query("Files", "SELECT", duration)
    except Exception as e:
        duration = time.time() - start
        track_database_query("Files", "SELECT", duration, error=e)
        raise
```

### API Response Time Middleware

```python
@app.before_request
def before_request():
    request._start_time = time.time()

@app.teardown_request
def log_request_time(exception):
    if hasattr(request, '_start_time'):
        from app.metrics import API_REQUEST_DURATION, API_REQUEST_ERRORS
        
        duration = time.time() - request._start_time
        endpoint = request.path
        method = request.method
        status = request._response.status_code if hasattr(request, '_response') else 500
        
        if exception:
            API_REQUEST_ERRORS.labels(endpoint=endpoint, error=type(exception).__name__).inc()
        
        API_REQUEST_DURATION.labels(endpoint=endpoint, method=method, status=status).observe(duration)
```

---

## 🎯 Benefits

### For Developers:
- **Visibility**: See performance bottlenecks in real-time
- **Debugging**: Trace slow queries and failed tasks
- **Performance Tuning**: A/B test optimizations
- **Alerting**: Get notified before issues affect users

### For Ops:
- **Uptime**: Health check endpoint for load balancers
- **Capacity Planning**: Monitor disk usage trends
- **Incident Response**: Quickly diagnose failures
- **Resource Optimization**: Right-size infrastructure

### For Management:
- **Dashboards**: Visualize metrics from Grafana
- **Reports**: Export data for presentations
- **KPIs**: Track SLA compliance
- **Cost Management**: Monitor resource efficiency

---

## 📅 Migration Checklist

For production deployment:

- [ ] Update docker-compose.yml to include Prometheus
- [ ] Update docker-compose.yml to include Grafana
- [ ] Create prometheus.yml configuration
- [ ] Import grafana_dashboard.json into Grafana
- [ ] Configure datasource in Grafana
- [ ] Test /api/metrics endpoint returns valid Prometheus format
- [ ] Test /api/health endpoint returns all services healthy
- [ ] Review /api/metrics logs to confirm no errors on startup
- [ ] Configure alerts for critical thresholds:
  - High error rate (>10%)
  - Slow database queries (>1s average)
  - Low disk space (<10% free)
  - Failed identifications (>20 failures/min)

---

## 🔍 Troubleshooting

### Metrics Not Updating

Symptom: `/api/metrics` returns 0 or empty values.

Checks:
1. **Is metrics.py imported?** Check logs for import errors
2. **Is metrics initialized?** Look for "Failed to initialize metrics" in logs
3. **Are connection errors logged?** Database connection could be failing
4. **Is Celery worker running?** If not, Celery metrics will be 0

Solution: Check logs: `tail -f logs/app.log | grep -i metric`

### Health Check Failing

Symptom: `/api/health` returns 503 (degraded).

Checks:
1. **Database connection failed?** Check DATABASE_URL and network connectivity
2. **Redis connection failed?** Redis not required for basic health checks
3. **Disk operations failed?** System may not have permissions for library paths

### Prometheus Scraping Errors

Symptom: Prometheus shows "connection refused" or "401 Unauthorized".

Checks:
1. **Is `/api/metrics` accessible?** Test: `curl http://localhost:8465/api/health`
2. **Is auth configured?** Add `basic_auth` to prometheus.yml with valid credentials
3. **Is firewall blocking?** Allow port 8465 from Prometheus server

---

## 📚 Documentation Links

- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
- [Grafana Dashboard Best Practices](https://grafana.com/docs/grafana/v9.0/dashboards/)
- [Prometheus Metrics Types](https://prometheus.io/docs/practices/naming/)
- [Histogram Configuration](https://prometheus.io/docs/practices/histograms/)
- [Alerting Best Practices](https://prometheus.io/docs/practices/alerting/)

---

## 📞 Support

For issues with Phase 3.2:
1. Check logs: `tail -f logs/app.log | grep -E "(metric|prometheus|health)`
2. Validate endpoint responses: `curl http://localhost:8465/api/health`
3. Test metrics: `curl -u admin:pass http://localhost:8465/api/metrics`
4. Review documentation: `PHASE_3_2_METRICS_MONITORING.md`

---

**Phase 3.2 Summary:**
- ✅ Metrics system created with Prometheus client
- ✅ Metrics `/api/metrics` and health `/api/health` endpoints
- ✅ Grafana dashboard JSON configuration (6 panels ready to import)
- ⚠️ Integration with Docker/production required (manual setup)
- ⚠️ Manual metrics integration in app code (optional, for detailed tracking)
- ⚠️ Alert rules require configuration in Prometheus
