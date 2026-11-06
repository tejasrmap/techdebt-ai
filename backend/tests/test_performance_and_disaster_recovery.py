import os
import time
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import SessionLocal
from app.models.all_models import User, Organization
from app.services.cache_service import CacheService
from app.services.disaster_recovery_service import DisasterRecoveryService

client = TestClient(app)

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def get_test_auth(role: str = "Administrator"):
    uid = uuid.uuid4().hex[:8]
    email = f"perf_{uid}@example.com"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": f"Admin User {uid}",
        "organization_name": f"Admin Org {uid}",
        "role": role
    })
    token = reg.json()["access_token"]
    org_id = reg.json()["user"]["org_id"]
    return {"Authorization": f"Bearer {token}"}, org_id

def test_cache_service_functionality_and_telemetry():
    CacheService.clear()

    # 1. Miss initially
    val = CacheService.get("user_key_1")
    assert val is None

    # 2. Set and hit
    CacheService.set("user_key_1", {"name": "Alice"}, ttl_seconds=5)
    cached = CacheService.get("user_key_1")
    assert cached == {"name": "Alice"}

    # 3. Stats
    stats = CacheService.get_stats()
    assert stats["hits"] >= 1
    assert stats["misses"] >= 1
    assert stats["items_count"] == 1

    # 4. Invalidate prefix
    CacheService.set("org_10_dash", "data1", ttl_seconds=60)
    CacheService.set("org_10_projects", "data2", ttl_seconds=60)
    CacheService.set("org_20_dash", "data3", ttl_seconds=60)

    count = CacheService.invalidate_prefix("org_10_")
    assert count == 2
    assert CacheService.get("org_10_dash") is None
    assert CacheService.get("org_20_dash") == "data3"

def test_disaster_recovery_backup_and_integrity(tmp_path):
    temp_backup_dir = str(tmp_path / "test_backups")

    # 1. Create backup
    manifest = DisasterRecoveryService.create_backup(custom_backup_dir=temp_backup_dir)
    assert manifest["backup_id"].startswith("backup_")
    assert manifest["sha256_checksum"] is not None
    assert manifest["vendor"] == "GT InnoX LLP"
    assert os.path.exists(manifest["file_path"])

    # 2. Verify integrity
    manifest_file = os.path.join(temp_backup_dir, f"{manifest['backup_id']}_manifest.json")
    is_valid = DisasterRecoveryService.verify_backup_integrity(manifest_file)
    assert is_valid is True

    # 3. List backups
    backups = DisasterRecoveryService.list_backups(custom_backup_dir=temp_backup_dir)
    assert len(backups) >= 1
    assert backups[0]["backup_id"] == manifest["backup_id"]
    assert backups[0]["verified"] is True

    # 4. Tamper with file and verify detection
    with open(manifest["file_path"], "ab") as f:
        f.write(b"corrupting_tamper_bytes")

    is_tampered_valid = DisasterRecoveryService.verify_backup_integrity(manifest_file)
    assert is_tampered_valid is False

def test_system_admin_api_endpoints_and_rbac(tmp_path):
    admin_headers, org_id = get_test_auth(role="Administrator")

    # 1. Cache stats endpoint
    resp_stats = client.get("/api/v1/system/cache/stats", headers=admin_headers)
    assert resp_stats.status_code == 200
    assert "items_count" in resp_stats.json()

    # 2. Cache clear endpoint
    resp_clear = client.post("/api/v1/system/cache/clear", headers=admin_headers)
    assert resp_clear.status_code == 200

    # 3. Disaster recovery backup list
    resp_backups = client.get("/api/v1/system/disaster-recovery/backups", headers=admin_headers)
    assert resp_backups.status_code == 200
    assert "backups" in resp_backups.json()
