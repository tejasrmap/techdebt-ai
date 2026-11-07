import uuid
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.repository_ingestion_service import (
    IngestionJobManager, ingestion_job_manager
)
from app.services.rate_limiter import rate_limiter

client = TestClient(app)

def get_auth_headers(email="async_user@techdebt.ai", org="Async Org"):
    rate_limiter.reset()
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Async Tester",
        "organization_name": org
    })
    if reg.status_code == 200:
        token = reg.json()["access_token"]
    else:
        login = client.post("/api/v1/auth/login", json={
            "email": email,
            "password": "SecurePassword123!"
        })
        token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_ingestion_job_manager_lifecycle():
    manager = IngestionJobManager()
    job_id = manager.create_job(project_id="proj_1", org_id="org_alpha", provider="github")
    assert job_id is not None

    job = manager.get_job(job_id, org_id="org_alpha")
    assert job["status"] == "pending"
    assert job["progress"] == 0

    # Advance job
    manager.update_job(job_id, status="cloning", progress=25, stage="Cloning remote repo")
    job = manager.get_job(job_id, org_id="org_alpha")
    assert job["status"] == "cloning"
    assert job["progress"] == 25
    assert job["started_at"] is not None

    # Complete job
    manager.update_job(job_id, status="completed", progress=100, stage="Done", results={"files": 42})
    job = manager.get_job(job_id, org_id="org_alpha")
    assert job["status"] == "completed"
    assert job["progress"] == 100
    assert job["results"]["files"] == 42
    assert job["completed_at"] is not None

def test_ingestion_job_tenant_isolation():
    manager = IngestionJobManager()
    job_id = manager.create_job(project_id="proj_a", org_id="org_a", provider="gitlab")

    # Visible to Org A
    assert manager.get_job(job_id, org_id="org_a") is not None

    # Hidden from Org B
    assert manager.get_job(job_id, org_id="org_b") is None

def test_ingestion_job_concurrency_limit():
    manager = IngestionJobManager()
    # Create up to limit
    for _ in range(manager.MAX_CONCURRENT_PER_ORG):
        manager.create_job(project_id="proj_x", org_id="org_busy")

    # Exceeding limit must raise ValueError
    with pytest.raises(ValueError) as exc:
        manager.create_job(project_id="proj_overflow", org_id="org_busy")
    assert "maximum concurrent ingestion limit" in str(exc.value)

def test_async_sync_and_poll_api():
    uid = uuid.uuid4().hex[:8]
    headers = get_auth_headers(email=f"async_{uid}@techdebt.ai", org=f"Async Org {uid}")
    # 1. Create a project with unique name
    proj_name = f"Async Ingest Proj {uid}"
    p_res = client.post("/api/v1/projects", json={"name": proj_name}, headers=headers)
    assert p_res.status_code in (200, 201)
    proj_id = p_res.json()["id"]

    # 2. Connect repository
    c_res = client.post("/api/v1/repositories/connect", json={
        "project_id": proj_id,
        "provider": "github",
        "repo_url": "https://github.com/octocat/Hello-World"
    }, headers=headers)
    assert c_res.status_code == 200

    # 3. Trigger async sync
    with patch("app.services.repository_ingestion_service.execute_async_ingestion") as mock_exec:
        sync_res = client.post(f"/api/v1/repositories/{proj_id}/sync-async", headers=headers)
        assert sync_res.status_code == 200
        data = sync_res.json()
        assert "job_id" in data
        job_id = data["job_id"]

        # 4. Poll status
        poll_res = client.get(f"/api/v1/repositories/jobs/{job_id}", headers=headers)
        assert poll_res.status_code == 200
        assert poll_res.json()["job_id"] == job_id
        assert poll_res.json()["status"] in ("pending", "cloning", "completed")
