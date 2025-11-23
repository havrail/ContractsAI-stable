# Celery + Redis + Flower Setup Guide

## Quick Start (Local Development)

### 1. Install Redis
```bash
# Windows (using Docker)
docker run -d -p 6379:6379 --name contractsai-redis redis:alpine

# Or install Redis for Windows
# Download from: https://github.com/microsoftarchive/redis/releases
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Start Services

**Terminal 1 - Redis (if not using Docker):**
```bash
redis-server
```

**Terminal 2 - Celery Worker:**
```bash
cd src_python
celery -A celery_app worker --loglevel=info --pool=solo
# Note: Use --pool=solo on Windows
```

**Terminal 3 - Flower (Monitoring):**
```bash
cd src_python
celery -A celery_app flower --port=5555
```

**Terminal 4 - FastAPI Backend:**
```bash
python run_dev.py
```

### 4. Access
- **API:** http://localhost:8000
- **Flower Dashboard:** http://localhost:5555
- **API Docs:** http://localhost:8000/docs

---

## Docker Deployment

### Start All Services
```bash
docker-compose up -d
```

### Services
- **backend:** FastAPI API (port 8000)
- **redis:** Message broker (port 6379)
- **celery-worker:** Background job processor
- **flower:** Celery monitoring (port 5555)

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f celery-worker
```

### Stop Services
```bash
docker-compose down
```

---

## How It Works

### Architecture
```
User → FastAPI → Celery Task → Redis Queue → Celery Worker → Pipeline → Database
                                              ↓
                                          Flower Dashboard
```

### Benefits
1. **Restart-Safe:** If app crashes, jobs continue in worker
2. **Distributed:** Run multiple workers on different machines
3. **Scalable:** Add more workers to process more jobs
4. **Monitored:** Flower provides real-time insights

### Job Flow
1. User submits analysis request to `/analyze`
2. API creates job in database (status: PENDING)
3. API dispatches Celery task with `task.delay(job_id, folder_path)`
4. Redis queues the task
5. Celery worker picks up task from queue
6. Worker runs pipeline, updates database
7. Job completes (status: COMPLETED/FAILED)

---

## Monitoring with Flower

Access: http://localhost:5555

**Features:**
- Active workers
- Task history
- Real-time task progress
- Retry failed tasks
- Task routing
- Resource usage (CPU, memory)

---

## Configuration

### Celery Settings (`celery_app.py`)
```python
task_time_limit = 3600  # 1 hour max
task_soft_time_limit = 3300  # 55 min soft limit
worker_prefetch_multiplier = 1  # One task at a time
worker_max_tasks_per_child = 50  # Restart after 50 tasks
```

### Environment Variables
```bash
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

---

## Production Tips

### 1. Scale Workers
```bash
# Single machine (4 workers)
celery -A celery_app worker --concurrency=4

# Multiple machines
# Run celery worker on each machine pointing to same Redis
```

### 2. Enable Autoscale
```bash
celery -A celery_app worker --autoscale=10,3
# Min 3 workers, max 10 workers
```

### 3. Periodic Tasks (Celery Beat)
Add to `celery_app.py`:
```python
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    'cleanup-old-jobs': {
        'task': 'tasks.cleanup_old_jobs',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
}
```

Start beat:
```bash
celery -A celery_app beat --loglevel=info
```

### 4. Monitoring & Alerts
- Use Flower for real-time monitoring
- Integrate with Prometheus for metrics
- Setup Sentry for error tracking

---

## Troubleshooting

### Worker Not Picking Up Tasks
```bash
# Check Redis connection
redis-cli ping
# Should return: PONG

# Check worker status
celery -A celery_app inspect active

# Purge queue
celery -A celery_app purge
```

### Task Stuck
- Check logs: `docker-compose logs celery-worker`
- Restart worker: `docker-compose restart celery-worker`
- Check task time limits

### High Memory Usage
- Reduce `worker_max_tasks_per_child`
- Enable autoscale
- Monitor with Flower

---

## Comparison: Before vs After

### Before (FastAPI BackgroundTasks)
- ❌ Not restart-safe
- ❌ Single process only
- ❌ No monitoring
- ❌ No retry mechanism
- ✅ Simple setup

### After (Celery)
- ✅ Restart-safe
- ✅ Distributed processing
- ✅ Flower monitoring
- ✅ Automatic retries
- ⚠️ More complex setup

---

## Commands Reference

```bash
# Start worker
celery -A celery_app worker --loglevel=info

# Start flower
celery -A celery_app flower

# Check active workers
celery -A celery_app inspect active

# Check queue stats
celery -A celery_app inspect stats

# Purge all tasks
celery -A celery_app purge

# Shutdown worker gracefully
celery -A celery_app control shutdown
```
