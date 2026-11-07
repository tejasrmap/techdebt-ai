# TechDebt AI v3.1.1 — Production Deployment Runbook
**Product:** TechDebt AI  
**Company:** GT InnoX LLP  
**Target Release:** v3.1.1  
**Target Platforms:** Docker Compose / Kubernetes / Linux Server (Ubuntu 22.04 LTS+)  

---

## 1. Pre-Deployment Environment Setup

### 1.1 Minimum System Requirements
- **Compute:** 4 vCPU, 8 GB RAM minimum (Production: 8 vCPU, 16 GB RAM recommended).
- **Storage:** 50 GB SSD for database and workspace caches.
- **Operating System:** Linux (Ubuntu 22.04 LTS or Debian 12 recommended) with Docker Engine 24+ and Docker Compose v2.
- **Database:** PostgreSQL 15+ with `uuid-ossp` or pgcrypto extension.
- **Cache/Queue:** Redis 7+.

### 1.2 Mandatory Environment Variables
Create `/etc/techdebt/.env` (or copy `.env.example`):

```bash
# General
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<generate-with-openssl-rand-hex-32>
ENCRYPTION_KEY=<generate-32-byte-base64-key>

# Database
DATABASE_URL=postgresql://techdebt_user:<secure_db_password>@postgres:5432/techdebt_production

# Redis & Caching
REDIS_URL=redis://redis:6379/0

# Rate Limiting & Proxies (CIDR list of trusted reverse proxies)
TRUSTED_PROXIES=127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16

# AI Providers (Optional but recommended for intelligent insights)
GEMINI_API_KEY=<your-google-ai-studio-key>
OPENAI_API_KEY=<your-openai-platform-key>

# VCS Integrations (Optional)
GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY_PATH=
GITLAB_INSTANCE_URL=https://gitlab.com
```

---

## 2. Standard Deployment Procedure

### Step 1: Clone or Unpack Release
```bash
mkdir -p /opt/techdebt-ai
cd /opt/techdebt-ai
unzip /tmp/techdebt-ai-v3.1.1-production.zip
```

### Step 2: Validate Environment & Secrets
```bash
# Verify no placeholder secrets exist
python -c "
import os
for k in ['SECRET_KEY', 'ENCRYPTION_KEY', 'DATABASE_URL']:
    v = os.getenv(k, '')
    assert v and 'placeholder' not in v.lower() and 'changeme' not in v.lower(), f'Insecure {k}'
"
```

### Step 3: Run Database Migrations
```bash
docker compose run --rm backend alembic upgrade head
```

### Step 4: Launch Core Services
```bash
docker compose up -d --remove-orphans
```

### Step 5: Verify Deployment Health
```bash
# Multi-component health check probe
curl -fsS http://localhost:8000/health | jq .

# Kubernetes liveness & readiness check
curl -fsS http://localhost:8000/live
curl -fsS http://localhost:8000/ready
```

---

## 3. Maintenance & Operational Procedures

### 3.1 Database Backup & Restore
```bash
# Automated Daily Backup
docker compose exec -T postgres pg_dump -U techdebt_user -d techdebt_production | gzip > /backups/techdebt_$(date +%Y%m%d_%H%M%S).sql.gz

# Restore Verification
gunzip -c /backups/techdebt_backup.sql.gz | docker compose exec -T postgres psql -U techdebt_user -d techdebt_production
```

### 3.2 Ingestion Workspace Maintenance
Stale analysis checkouts are cleaned up automatically by `cleanup_expired_workspaces()`. To perform an immediate manual purge:
```bash
docker compose exec backend python -c "
from app.services.repository_ingestion_service import repository_ingestion_service
repository_ingestion_service.cleanup_expired_workspaces(max_age_hours=6)
"
```

### 3.3 Zero-Downtime Rollback Procedure
If a production issue occurs:
1. Revert container image tag to previous stable build (`v3.1.0` or prior SHA).
2. If database migration needs rollback:
   ```bash
   docker compose run --rm backend alembic downgrade -1
   ```
3. Restart containers:
   ```bash
   docker compose up -d --force-recreate
   ```

