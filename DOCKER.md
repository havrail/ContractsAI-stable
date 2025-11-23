# ContractsAI Docker Deployment Guide

## Quick Start

### 1. Prerequisites
- Docker Desktop installed
- Docker Compose installed
- LM Studio running (or access to LLM endpoint)

### 2. Configuration
```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings
# Set API_KEY, LM_STUDIO_IP, etc.
```

### 3. Build and Run
```bash
# Build the image
docker-compose build

# Start services
docker-compose up -d

# View logs
docker-compose logs -f backend
```

### 4. Access Application
- Backend API: http://localhost:8000
- Health Check: http://localhost:8000/health
- Metrics: http://localhost:8000/metrics
- API Docs: http://localhost:8000/docs

## Commands

### Start Services
```bash
docker-compose up -d
```

### Stop Services
```bash
docker-compose down
```

### View Logs
```bash
# All services
docker-compose logs -f

# Backend only
docker-compose logs -f backend
```

### Rebuild After Code Changes
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Access Container Shell
```bash
docker exec -it contractsai-backend bash
```

## Environment Variables

Required in `.env`:
```bash
API_KEY=your-production-api-key
LM_STUDIO_IP=http://your-llm-server:1234
MAX_WORKERS=4
USE_VISION_MODEL=false
ENVIRONMENT=production
```

## Volumes

Data is persisted in:
- `./src_python/contracts_ai.db` - SQLite database
- `./exports/` - Excel reports
- `./logs/` - Application logs

## Networking

### Connect to LM Studio on Host Machine
Windows/Mac:
```bash
LM_STUDIO_IP=http://host.docker.internal:1234
```

Linux:
```bash
LM_STUDIO_IP=http://172.17.0.1:1234
```

### Custom Network
Services run on `contractsai-network` bridge network.

## Production Deployment

### 1. Use Production .env
```bash
cp .env.example .env.production
# Edit with production values
```

### 2. Run with Production Config
```bash
docker-compose --env-file .env.production up -d
```

### 3. Enable HTTPS (Nginx Reverse Proxy)
```nginx
server {
    listen 443 ssl;
    server_name contracts.yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker-compose logs backend

# Check if port 8000 is already in use
netstat -an | findstr :8000  # Windows
lsof -i :8000  # Linux/Mac
```

### Database Locked
```bash
# Stop services
docker-compose down

# Remove database lock (if safe)
rm ./src_python/contracts_ai.db-shm
rm ./src_python/contracts_ai.db-wal

# Restart
docker-compose up -d
```

### LLM Connection Failed
```bash
# Test from container
docker exec contractsai-backend curl http://host.docker.internal:1234

# Check LM Studio is running and accessible
# Update LM_STUDIO_IP in .env
```

## Monitoring

### Health Check
```bash
curl http://localhost:8000/health
```

### Metrics
```bash
curl http://localhost:8000/metrics | jq
```

### Container Stats
```bash
docker stats contractsai-backend
```

## Backup

### Database Backup
```bash
# While running
docker exec contractsai-backend sqlite3 /app/src_python/contracts_ai.db ".backup '/app/exports/backup.db'"

# Or copy from host
cp ./src_python/contracts_ai.db ./backups/contracts_ai_$(date +%Y%m%d).db
```

## Scaling

### Increase Workers
```bash
# In .env
MAX_WORKERS=8

# Restart
docker-compose restart backend
```

### Multiple Backend Instances (Load Balancer)
```yaml
# docker-compose.yml
services:
  backend:
    deploy:
      replicas: 3
```

## Updates

### Pull Latest Code
```bash
git pull origin main
docker-compose down
docker-compose build
docker-compose up -d
```

### Database Migrations
```bash
# Access container
docker exec -it contractsai-backend bash

# Run migrations
cd src_python
alembic upgrade head
```
