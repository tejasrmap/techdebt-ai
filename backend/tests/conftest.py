import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest
from sqlalchemy import text
from app.services.rate_limiter import rate_limiter
from app.database import SessionLocal, Base, engine
from app.models.all_models import *

@pytest.fixture(autouse=True, scope="session")
def setup_database_schema():
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        for col_sql in [
            "ALTER TABLE projects ADD COLUMN is_archived BOOLEAN DEFAULT 0",
            "ALTER TABLE projects ADD COLUMN archived_at DATETIME",
            "ALTER TABLE users ADD COLUMN password_changed_at DATETIME",
            "ALTER TABLE ai_usage_ledgers ADD COLUMN cost_usd FLOAT DEFAULT 0.0",
            "ALTER TABLE ai_usage_ledgers ADD COLUMN latency_ms FLOAT DEFAULT 0.0",
            "ALTER TABLE technologies ADD COLUMN license VARCHAR(150) DEFAULT 'UNKNOWN'",
            "ALTER TABLE project_technologies ADD COLUMN latest_version VARCHAR(100) DEFAULT 'unknown'",
            "ALTER TABLE project_technologies ADD COLUMN is_outdated BOOLEAN DEFAULT 0",
            "ALTER TABLE project_technologies ADD COLUMN license VARCHAR(150) DEFAULT 'UNKNOWN'",
            "ALTER TABLE project_technologies ADD COLUMN vulnerability_status VARCHAR(50) DEFAULT 'UNKNOWN'",
            "ALTER TABLE assessments ADD COLUMN commit_sha VARCHAR(100) DEFAULT ''",
            "ALTER TABLE assessments ADD COLUMN analyzer_version VARCHAR(50) DEFAULT '3.1.0'",
            "ALTER TABLE risk_findings ADD COLUMN estimated_remediation_hours FLOAT DEFAULT 2.0",
            "ALTER TABLE risk_findings ADD COLUMN fingerprint VARCHAR(128)",
            "ALTER TABLE code_findings ADD COLUMN status VARCHAR(50) DEFAULT 'Open'",
            "ALTER TABLE code_findings ADD COLUMN assigned_to VARCHAR(36)",
            "ALTER TABLE code_findings ADD COLUMN resolved_at DATETIME",
            "ALTER TABLE code_findings ADD COLUMN analyzer_name VARCHAR(100) DEFAULT 'SourceCodeAnalyzer'",
            "ALTER TABLE code_findings ADD COLUMN analyzer_version VARCHAR(50) DEFAULT '3.1.0'",
            "ALTER TABLE subscriptions ADD COLUMN payment_provider VARCHAR(50) DEFAULT 'razorpay'",
            "ALTER TABLE subscriptions ADD COLUMN provider_customer_id VARCHAR(255) DEFAULT ''",
            "ALTER TABLE subscriptions ADD COLUMN provider_subscription_id VARCHAR(255) DEFAULT ''",
            "ALTER TABLE subscriptions ADD COLUMN provider_order_id VARCHAR(255) DEFAULT ''",
            "ALTER TABLE subscriptions ADD COLUMN provider_payment_id VARCHAR(255) DEFAULT ''"
        ]:
            try:
                conn.execute(text(col_sql))
                conn.commit()
            except Exception:
                pass
    try:
        from app.seed_data import seed
        seed()
    except Exception:
        pass

@pytest.fixture(autouse=True)
def reset_rate_limiter_and_db():
    rate_limiter.reset()
    yield
    rate_limiter.reset()

