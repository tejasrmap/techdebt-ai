# TechDebt AI v1.0.9 — Production Deployment Guide

**Target Audience:** DevOps Engineers, Platform Engineers, System Administrators  
**Product:** TechDebt AI – Technology Debt Review Assistant  
**Release Version:** v1.0.9  

---

## 1. System Architecture Overview

In production, TechDebt AI runs as 4 containerized services managed by Docker Compose or Kubernetes:

```
[ Client Browser ]
        │
        ▼ (Port 80 HTTP / 443 HTTPS)
┌──────────────────────────────────────────────┐
│  frontend: Nginx Alpine Reverse Proxy        │
│  - Serves compiled React 19 SPA assets       │
│  - Proxies /api/ requests to backend:8000    │
└──────────────────────┬───────────────────────┘
                       │ (Internal Docker Network)
                       ▼
┌──────────────────────────────────────────────┐
│  backend: FastAPI Application Server         │
│  - Runs Alembic migrations on startup        │
│  - Serves authenticated REST API endpoints   │
│  - APScheduler IS DISABLED HERE              │
└──────────────────────┬───────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
┌───────────────────────┐   ┌──────────────────────────────────────────────┐
│  db: PostgreSQL 15    │   │  worker: Dedicated Background Review Worker  │
│  - Persistent Volume  │◄──┤  - APScheduler active                        │
│  - 127.0.0.1:5432     │   │  - Atomic distributed locking & fencing      │
│  - Multi-tenant data  │   │  - Periodic sync of database schedules      │
└───────────────────────┘   └──────────────────────────────────────────────┘
```

---

## 2. Environment Variables & Secret Configuration

Production deployments require a securely populated `.env` file based on `.env.example`.

### Mandatory Production Variables

| Variable | Description | Example / Generation Command |
|---|---|---|
| `ENVIRONMENT` | Must be set to `production` | `production` |
| `POSTGRES_USER` | PostgreSQL superuser username | `techdebt_admin` |
| `POSTGRES_PASSWORD` | PostgreSQL superuser password (min 16 chars) | `openssl rand -base64 24` |
| `POSTGRES_DB` | Production database name | `techdebt_production` |
| `SECRET_KEY` | JWT signing secret (min 32 chars) | `openssl rand -hex 32` |
| `ENCRYPTION_KEY` | Fernet 32-byte url-safe base64 encryption key | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `CORS_ORIGINS` | Explicit comma-separated allowed web origins | `https://techdebt.yourdomain.com` |
| `ENABLE_DEMO_SEED` | Must remain `false` in production | `false` |
| `ALLOW_PLATFORM_INTEGRATION_FALLBACK` | Allow platform API keys if org key absent | `false` |

> [!IMPORTANT]
> The production configuration validator will **refuse to boot** if default, placeholder (`replace-with`, `change-me`, `your-secret`), or empty secrets are provided.

---

## 3. Deployment Steps via Docker Compose

### Step 1: Clone Repository & Prepare Directory
```bash
git clone https://github.com/gtinnox/techdebt-ai.git /opt/techdebt-ai
cd /opt/techdebt-ai
```

### Step 2: Configure Production Secrets
```bash
cp .env.example .env
chmod 600 .env
nano .env  # Populate mandatory variables listed above
```

### Step 3: Validate Compose Configuration
```bash
docker compose config
```
If any required variable is missing or malformed, the command will fail with an error identifying the missing variable.

### Step 4: Build and Launch Services
```bash
docker compose up -d --build
```

### Step 5: Verify Container Health
```bash
docker compose ps
```
Expected output:
- `techdebt_postgres`: `Up (healthy)`
- `techdebt_backend`: `Up (healthy)`
- `techdebt_worker`: `Up`
- `techdebt_frontend`: `Up`

### Step 6: Monitor Application Logs
```bash
docker compose logs -f backend
docker compose logs -f worker
```

---

## 4. Maintenance & Operations Runbook

### Database Migrations
Migrations run automatically on backend startup. To run migrations manually:
```bash
docker compose exec backend python -m alembic upgrade head
```

### Checking Active Distributed Locks
```bash
docker compose exec db psql -U postgres -d techdebt_db -c "SELECT * FROM distributed_locks;"
```

### Purging Expired Session Tokens
```bash
docker compose exec backend python -c "from app.database import SessionLocal; from app.services.auth_service import purge_expired_revoked_tokens; db=SessionLocal(); purge_expired_revoked_tokens(db); db.close()"
```

### Backup Database
```bash
docker compose exec -T db pg_dump -U postgres techdebt_db | gzip > "techdebt_backup_$(date +%Y%m%d_%H%M%S).sql.gz"
```

### Restore Database
```bash
gunzip -c techdebt_backup_20261106_120000.sql.gz | docker compose exec -T db psql -U postgres techdebt_db
```

---

## 5. Security Checklist Before Going Live

- [ ] `ENVIRONMENT` is set to `production`.
- [ ] `ENABLE_DEMO_SEED` is set to `false`.
- [ ] `POSTGRES_PASSWORD`, `SECRET_KEY`, and `ENCRYPTION_KEY` are cryptographically random.
- [ ] Direct backend port (8000) and database port (5432) are bound to `127.0.0.1` and not exposed to the public internet.
- [ ] TLS termination (HTTPS) is configured on port 443 with a valid certificate (e.g. Let's Encrypt / Certbot).
- [ ] Organization-specific API keys for Firecrawl and LLM providers are configured via the web UI.

