# Testing Guide for Docker/Portainer Deployment

## Quick Diagnostic Steps

### 1. Check System Diagnostic Endpoint

After deploying the new version, access:
```
http://your-server:8465/api/system/diagnostic
```

This will show:
- Current process ID
- Redis connection status
- Emitter configuration
- Active jobs

**Look for**:
- `redis_url_configured`: should be `true`
- `redis_connected`: should be `true`
- `emitter_configured`: should be `true`

---

### 2. Monitor Container Logs

#### Worker Logs (Most Important)
```bash
docker logs myfoil-worker -f --tail=100
```

**What to look for**:
- `[JobTracker PID:XXX] Initializing with REDIS_URL=redis://redis:6379/0`
- `[SocketIO PID:XXX] ✅ Broadcast emitter created successfully`
- `[JobTracker PID:XXX] 🚀 Starting new job: id=scan_...`
- `[SocketIO PID:XXX] 📤 Emitting event 'job_update'`
- `[SocketIO PID:XXX] ✅ Successfully emitted 'job_update'`

**Red flags**:
- `⚠️ No REDIS_URL environment variable`
- `❌ Failed to create SocketIO emitter`
- `⚠️ No emitter configured, cannot send updates to UI!`

#### App Logs
```bash
docker logs myfoil -f --tail=100
```

**What to look for**:
- SocketIO connection messages from clients
- Job update events being received

#### Redis Logs
```bash
docker logs myfoil-redis -f --tail=50
```

---

### 3. Trigger a Test Scan

Via API:
```bash
curl -X POST http://localhost:8465/api/library/scan \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION_COOKIE" \
  -d '{"path": null}'
```

Or via UI:
1. Go to Settings → Library
2. Click "Scan" button on any library path

---

### 4. Check Redis Directly

```bash
# Enter Redis container
docker exec -it myfoil-redis redis-cli

# Check for job keys
KEYS job:*

# Check active jobs set
SMEMBERS jobs:active

# Check job details
GET job:scan_1234567890

# Monitor pub/sub channels
PUBSUB CHANNELS

# Subscribe to flask-socketio channel
SUBSCRIBE flask-socketio
```

While subscribed, trigger a scan in another terminal and watch for messages.

---

### 5. Check Docker Network

Verify all containers are on the same network:
```bash
docker network inspect myfoil_default
```

All three containers (redis, myfoil, worker) should be listed.

---

## Troubleshooting Scenarios

### Scenario 1: Worker can't connect to Redis

**Symptoms**:
- Worker logs show: `❌ Failed to create SocketIO emitter`
- Diagnostic shows: `redis_connected: false`

**Fix**:
```bash
# Check if Redis is running
docker ps | grep redis

# Check Redis health
docker inspect myfoil-redis | grep Health

# Restart Redis
docker restart myfoil-redis

# Restart worker
docker restart myfoil-worker
```

### Scenario 2: Emitter not configured

**Symptoms**:
- Worker logs show: `⚠️ No emitter configured`
- Jobs are created but UI doesn't update

**Cause**: Worker initialized emitter before Redis was ready

**Fix**:
```bash
# Restart worker (will recreate emitter)
docker restart myfoil-worker
```

### Scenario 3: Jobs appear in Redis but not in UI

**Symptoms**:
- `SMEMBERS jobs:active` shows jobs
- UI shows "No active operations"

**Cause**: SocketIO not receiving pub/sub messages

**Debug**:
```bash
# In Redis CLI
PUBSUB CHANNELS
# Should show: flask-socketio

# Subscribe to it
SUBSCRIBE flask-socketio
# Trigger a scan, you should see messages
```

**Fix**: Check if app container has REDIS_URL configured:
```bash
docker exec myfoil env | grep REDIS_URL
```

---

## Expected Log Flow (Happy Path)

### 1. Worker Startup
```
[JobTracker PID:42] Initializing with REDIS_URL=redis://redis:6379/0
[JobTracker PID:42] Connected to Redis at redis://redis:6379/0
[SocketIO PID:42] Creating new emitter with REDIS_URL=redis://redis:6379/0
[SocketIO PID:42] ✅ Broadcast emitter created successfully
[JobTracker PID:42] Emitter configured: True
```

### 2. Scan Triggered
```
[JobTracker PID:42] 🚀 Starting new job: id=scan_1737649800, type=library_scan
[JobTracker PID:42] ✅ Job scan_1737649800 started and saved to Redis
[JobTracker PID:42] 📡 Calling emitter for 'job_update' event...
[SocketIO PID:42] 📤 Emitting event 'job_update' with broadcast=True, namespace='/'
[SocketIO PID:42] ✅ Successfully emitted 'job_update' (broadcast=True, namespace='/')
[JobTracker PID:42] ✅ Successfully emitted job_update - 1 active, 0 in history
```

### 3. Progress Updates
```
[JobTracker PID:42] 📡 Calling emitter for 'job_update' event...
[SocketIO PID:42] 📤 Emitting event 'job_update'...
[SocketIO PID:42] ✅ Successfully emitted 'job_update'
```

### 4. Scan Completed
```
[JobTracker PID:42] 📡 Calling emitter for 'job_update' event...
[SocketIO PID:42] ✅ Successfully emitted 'job_update' - 0 active, 1 in history
```

---

## Next Steps if Still Not Working

If after all this the issue persists, we need to:

1. **Verify Docker Compose volumes match** between app and worker
2. **Check if both containers see the same file system**
3. **Test with minimal reproduction** using `test_redis_emit.py`
4. **Consider fallback to HTTP polling** instead of WebSockets

Contact with the exact error messages from the logs for further assistance.
