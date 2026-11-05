# TechDebt AI v1.0.9 — Database Migration Guide

**Product:** TechDebt AI – Technology Debt Review Assistant  
**Database Engines Supported:** PostgreSQL 15+ (Production) & SQLite 3.35+ (Development)  
**Migration Tool:** Alembic 1.13+  
**Release Version:** v1.0.9  

---

## 1. Migration Architecture & Directory Layout

Database schema versioning is managed strictly via Alembic. Schema mutations must never rely on `Base.metadata.create_all()` in production environments.

```
backend/
├── alembic.ini                   # Alembic configuration (configured dynamically)
└── alembic/
    ├── env.py                    # Migration execution environment script
    ├── script.py.mako            # Migration template
    └── versions/
        ├── 001_initial_complete_schema.py                      # Comprehensive baseline schema (17 tables)
        └── 002_transactional_fencing_and_memento_cleanup.py   # Transactional fencing columns & Memento cleanup
```

---

## 2. Migration History

### Migration 001: Baseline Schema (`001_initial_complete_schema`)
Establishes the initial 17 core relational tables including `distributed_locks`, `assessments`, `technologies`, `historical_assessments`, etc.

### Migration 002: Transactional Fencing & Memento Cleanup (`002_transactional_fencing_and_memento_cleanup`)
- Adds `fencing_generation` column (INTEGER NOT NULL DEFAULT 1) to:
  - `assessments`
  - `review_jobs`
  - `historical_assessments`
- Drops obsolete Memento columns (`memento_api_key`, `memento_endpoint`) from `integration_settings` table.
- Retains PostgreSQL as the authoritative multi-tenant longitudinal historical storage provider.

1. **`organizations`**: Multi-tenant boundary root with unique name and slug.
2. **`users`**: Tenant user accounts with bcrypt hashed passwords and RBAC roles (`Administrator`, `Engineering Manager`, `Developer`, `Viewer`).
3. **`organization_invitations`**: SHA-256 hashed single-use invitation tokens with expiration.
4. **`revoked_tokens`**: Revoked JWT `jti` blocklist table for instantaneous logout invalidation.
5. **`projects`**: Tenant software repositories with language, framework, and metadata columns.
6. **`technologies`**: Catalog of software packages, ecosystem tags, latest stable versions, and deprecation flags.
7. **`project_technologies`**: Association linking projects to technologies with installed versions and file sources.
8. **`assessments`**: Assessment records storing overall health score, confidence, and summaries.
9. **`technology_scores`**: 8-dimension weighted scores per evaluated technology.
10. **`risk_findings`**: Actionable debt findings with severity (`Critical`, `High`, `Medium`, `Low`) and lifecycle status.
11. **`evidence_sources`**: External evidence URLs, citations, reliability metrics, and official flags.
12. **`historical_assessments`**: Longitudinal historical memory records with delta tracking (PostgreSQL Authoritative).
13. **`scheduled_reviews`**: Recurring review definitions with cron expressions and next run timestamps.
14. **`review_jobs`**: Background worker review execution history and error logs.
15. **`audit_logs`**: Immutable audit logs of administrative and operational actions.
16. **`integration_settings`**: Tenant integration credentials encrypted at rest with Fernet.
17. **`distributed_locks`**: Atomic distributed locking table with `lock_key`, `owner_id`, `generation`, `acquired_at`, and `expires_at`.

---

## 3. Running Migrations

### Production Environment (PostgreSQL)
Alembic migrations apply automatically on container boot via `app.main:lifespan`:
```bash
# Verify status
docker compose exec backend python -m alembic current

# Upgrade to latest revision
docker compose exec backend python -m alembic upgrade head
```

### Local Development (SQLite)
```bash
cd backend
$env:PYTHONPATH="."
python -m alembic upgrade head
```

---

## 4. Rollback and Re-upgrade Verification

To verify migration reversibility on a temporary database without affecting production data:

```bash
# 1. Roll back schema completely to base (drops all tables in reverse topological order)
python -m alembic downgrade base

# 2. Re-apply all migrations to head
python -m alembic upgrade head
```

Automated verification of this rollback and re-upgrade sequence is continuously tested in `test_audit_fixes.py::test_safe_database_migration_downgrade_and_upgrade_on_disposable_db` using isolated disposable databases in OS temporary storage.

