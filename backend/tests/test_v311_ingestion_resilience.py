import uuid
import pytest
from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models.all_models import Organization, Project, RepositoryIngestionRun, RepositoryConnection
from app.services.repository_ingestion_service import (
    IngestionJobManager,
    SYNC_STATE_QUEUED,
    SYNC_STATE_CLONING,
    SYNC_STATE_CANCELLED,
    SYNC_STATE_FAILED,
)

def test_ingestion_job_cancellation():
    db = SessionLocal()
    org_id = str(uuid.uuid4())
    proj_id = str(uuid.uuid4())
    org = Organization(id=org_id, name=f"Cancel Org {uuid.uuid4().hex[:6]}", slug=f"cancel-org-{uuid.uuid4().hex[:6]}")
    proj = Project(id=proj_id, org_id=org_id, name="Cancel Test Project")
    db.add_all([org, proj])
    db.commit()

    try:
        manager = IngestionJobManager(persist_db=True)
        job_id = manager.create_job(project_id=proj_id, org_id=org_id, provider="github")
        
        job = manager.get_job(job_id, org_id=org_id)
        assert job["sync_state"] == SYNC_STATE_QUEUED

        # Cancel the job
        cancelled = manager.cancel_job(job_id, org_id=org_id)
        assert cancelled is True

        job_after = manager.get_job(job_id, org_id=org_id)
        assert job_after["sync_state"] == SYNC_STATE_CANCELLED
    finally:
        db.close()

def test_ingestion_stalled_job_recovery():
    db = SessionLocal()
    org_id = str(uuid.uuid4())
    proj_id = str(uuid.uuid4())
    org = Organization(id=org_id, name=f"Stall Org {uuid.uuid4().hex[:6]}", slug=f"stall-org-{uuid.uuid4().hex[:6]}")
    proj = Project(id=proj_id, org_id=org_id, name="Stall Test Project")
    db.add_all([org, proj])
    db.commit()

    try:
        # Simulate an orphaned run from a crashed worker that started 2 hours ago
        stalled_run = RepositoryIngestionRun(
            id=str(uuid.uuid4()),
            org_id=org_id,
            project_id=proj_id,
            provider="github",
            branch="main",
            status=SYNC_STATE_CLONING,
            created_at=datetime.utcnow() - timedelta(hours=2),
            started_at=datetime.utcnow() - timedelta(hours=2),
        )
        db.add(stalled_run)
        db.commit()

        manager = IngestionJobManager(persist_db=True)
        recovered = manager.recover_stalled_jobs(timeout_minutes=45)
        assert recovered >= 1

        db.refresh(stalled_run)
        assert stalled_run.status == SYNC_STATE_FAILED
        assert "timed out or worker process terminated" in stalled_run.error_message
    finally:
        db.close()

