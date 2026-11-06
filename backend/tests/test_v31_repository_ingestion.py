import asyncio
import hashlib
import hmac
import io
import json
import os
import uuid
import zipfile
from unittest.mock import patch
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.all_models import (
    Assessment,
    CodeFinding,
    Project,
    ProjectTechnology,
    RepositoryAnalysisSnapshot,
    RepositoryConnection,
    RepositoryIngestionRun,
)
from app.services.bitbucket_service import BitbucketService
from app.services.rate_limiter import rate_limiter
from app.services.repository_ingestion_service import (
    ArchiveSecurityError,
    RepositoryIngestionService,
    RepositorySyncError,
    SYNC_STATE_COMPLETED,
    SYNC_STATE_FAILED,
    UnsafeRepositoryURLError,
    execute_async_ingestion,
    ingestion_job_manager,
)
from app.services.scheduler_service import execute_project_review

client = TestClient(app)


def _auth_headers() -> tuple[dict, str]:
    rate_limiter.reset()
    uid = uuid.uuid4().hex[:8]
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ingest_v31_{uid}@techdebt.ai",
            "password": "SecurePassword123!",
            "full_name": f"Ingest Engineer {uid}",
            "organization_name": f"Ingest Org {uid}",
        },
    )
    assert res.status_code == 200
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["org_id"]


def _grant_enterprise_for_multi_project_test(org_id: str) -> None:
    from app.models.all_models import Organization, Subscription, SubscriptionPlan
    from app.services.billing_service import BillingService

    db = SessionLocal()
    try:
        BillingService._ensure_standard_plans(db)
        org = db.query(Organization).filter(Organization.id == org_id).first()
        ent_plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == "enterprise").first()
        if org and ent_plan:
            org.plan = "enterprise"
            sub = BillingService.get_or_create_subscription(db, org_id)
            sub.plan_id = ent_plan.id
            sub.status = "active"
            db.commit()
    finally:
        db.close()


def _build_sample_repo_zip(wrapper_prefix: str = "sample-repo-a1b2c3d/") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            f"{wrapper_prefix}app/service.py",
            (
                "import subprocess\n\n"
                "def run_untrusted(cmd: str):\n"
                "    eval('1 + 1')\n"
                "    return subprocess.run(cmd, shell=True)\n"
            ),
        )
        zf.writestr(
            f"{wrapper_prefix}requirements.txt",
            "fastapi==0.109.2\nrequests==2.31.0\n",
        )
        zf.writestr(
            f"{wrapper_prefix}package.json",
            json.dumps(
                {
                    "name": "web-ui",
                    "version": "1.0.0",
                    "dependencies": {"react": "^18.2.0"},
                }
            ),
        )
        zf.writestr(
            f"{wrapper_prefix}tests/test_service.py",
            "def test_smoke():\n    assert 1 + 1 == 2\n",
        )
    return buf.getvalue()


def test_zip_upload_persists_durable_snapshot_and_runs_assessment_without_temp_dir():
    headers, org_id = _auth_headers()
    _grant_enterprise_for_multi_project_test(org_id)

    proj = client.post("/api/v1/projects", json={"name": f"ZIP Durable {uuid.uuid4().hex[:6]}"}, headers=headers).json()
    project_id = proj["id"]

    zip_bytes = _build_sample_repo_zip(wrapper_prefix="")
    up_res = client.post(
        "/api/v1/repositories/upload-zip",
        data={"project_id": project_id, "branch": "main"},
        files={"file": ("service-archive.zip", zip_bytes, "application/zip")},
        headers=headers,
    )
    assert up_res.status_code == 200, up_res.text
    up_body = up_res.json()
    assert up_body["sync_state"] == SYNC_STATE_COMPLETED
    assert up_body["dependencies_discovered"] == 3
    assert up_body["findings_discovered"] >= 1
    assert up_body["commit_sha"].startswith("zip:")

    # Verify idempotent re-upload of identical ZIP does not duplicate snapshots or ProjectTechnology rows
    up_res_2 = client.post(
        "/api/v1/repositories/upload-zip",
        data={"project_id": project_id, "branch": "main"},
        files={"file": ("service-archive.zip", zip_bytes, "application/zip")},
        headers=headers,
    )
    assert up_res_2.status_code == 200
    assert up_res_2.json()["idempotent_reused"] is True

    db = SessionLocal()
    try:
        snaps = db.query(RepositoryAnalysisSnapshot).filter(RepositoryAnalysisSnapshot.project_id == project_id).all()
        assert len(snaps) == 1
        conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
        assert conn is not None
        # Temporary directory is NOT retained on disk; assessment must succeed purely from persisted snapshot
        assert conn.local_path is None

        pts = db.query(ProjectTechnology).filter(ProjectTechnology.project_id == project_id).all()
        assert len(pts) == 3
        versions = {pt.technology.name.lower(): pt.installed_version for pt in pts}
        assert versions["fastapi"] == "0.109.2"
        assert versions["requests"] == "2.31.0"
        assert versions["react"] == "18.2.0"

        assessment = asyncio.run(execute_project_review(project_id=project_id, trigger_type="scheduled", db_session=db))
        assert assessment.status == "completed"
        assert assessment.commit_sha == snaps[0].commit_sha
        assert assessment.lines_of_code > 0
        assert assessment.files_analyzed >= 2
        assert assessment.raw_output is not None
        assert assessment.raw_output["snapshot_id"] == snaps[0].id

        persisted_findings = db.query(CodeFinding).filter(CodeFinding.assessment_id == assessment.id).all()
        assert len(persisted_findings) >= 1
    finally:
        db.close()


@pytest.mark.parametrize("provider", ["github", "gitlab", "bitbucket"])
def test_remote_providers_end_to_end_ingestion_persistence_and_redirect_token_hygiene(provider: str):
    headers, org_id = _auth_headers()
    _grant_enterprise_for_multi_project_test(org_id)

    proj = client.post(
        "/api/v1/projects",
        json={"name": f"Remote {provider.title()} {uuid.uuid4().hex[:6]}"},
        headers=headers,
    ).json()
    project_id = proj["id"]

    repo_urls = {
        "github": "https://github.com/gt-innox/platform-core",
        "gitlab": "https://gitlab.com/gt-innox/platform-core",
        "bitbucket": "https://bitbucket.org/gt-innox/platform-core",
    }
    expected_sha = f"{provider[:2]}9f8e7d6c5b4a392817263544556677889900aa"[:40]
    secret_pat = f"secret_{provider}_pat_token_998877"

    c_res = client.post(
        "/api/v1/repositories/connect",
        json={
            "project_id": project_id,
            "provider": provider,
            "repo_url": repo_urls[provider],
            "branch": "main",
            "access_token": secret_pat,
        },
        headers=headers,
    )
    assert c_res.status_code == 200
    assert c_res.json()["credentials_stored"] is True
    assert "webhook_secret" in c_res.json()

    zip_payload = _build_sample_repo_zip(wrapper_prefix=f"platform-core-{expected_sha[:7]}/")
    observed_requests: list[tuple[str, dict]] = []

    async def mock_http_get(self_client, url: str, headers: dict = None, **kwargs):
        req_hdrs = dict(headers or {})
        observed_requests.append((url, req_hdrs))
        req = httpx.Request("GET", url, headers=req_hdrs)

        if provider == "github":
            if "/commits/" in url:
                assert req_hdrs.get("Authorization") == f"Bearer {secret_pat}"
                return httpx.Response(
                    200,
                    json={
                        "sha": expected_sha,
                        "commit": {"message": "feat: harden github sync", "author": {"name": "Alice"}},
                    },
                    request=req,
                )
            if "api.github.com/repos/" in url and "/zipball/" in url:
                assert req_hdrs.get("Authorization") == f"Bearer {secret_pat}"
                return httpx.Response(
                    302,
                    headers={"Location": f"https://codeload.github.com/gt-innox/platform-core/legacy.zip/{expected_sha}"},
                    request=req,
                )
            if "codeload.github.com" in url:
                # Authorization header MUST be stripped on cross-host redirect!
                assert "Authorization" not in req_hdrs
                return httpx.Response(200, content=zip_payload, request=req)

        elif provider == "gitlab":
            if "/repository/commits/" in url:
                assert req_hdrs.get("Authorization") == f"Bearer {secret_pat}"
                return httpx.Response(
                    200,
                    json={"id": expected_sha, "message": "feat: gitlab sync", "author_name": "Bob"},
                    request=req,
                )
            if "/repository/archive.zip" in url:
                return httpx.Response(200, content=zip_payload, request=req)

        elif provider == "bitbucket":
            if "/commit/" in url:
                assert req_hdrs.get("Authorization") == f"Bearer {secret_pat}"
                return httpx.Response(
                    200,
                    json={"hash": expected_sha, "message": "feat: bitbucket sync", "author": {"raw": "Carol"}},
                    request=req,
                )
            if "/get/" in url and url.endswith(".zip"):
                return httpx.Response(200, content=zip_payload, request=req)

        return httpx.Response(404, json={"message": "Not found"}, request=req)

    job_id = ingestion_job_manager.create_job(project_id=project_id, org_id=org_id, provider=provider, branch="main")
    with patch.object(httpx.AsyncClient, "get", new=mock_http_get), patch.object(
        RepositoryIngestionService, "validate_repository_url", side_effect=lambda u: u
    ):
        asyncio.run(
            execute_async_ingestion(
                job_id=job_id,
                project_id=project_id,
                org_id=org_id,
                repo_url=repo_urls[provider],
                auth_token=None,  # Must decrypt stored token automatically
                branch="main",
                provider=provider,
            )
        )

    job_state = ingestion_job_manager.get_job(job_id, org_id=org_id)
    assert job_state is not None
    assert job_state["sync_state"] == SYNC_STATE_COMPLETED
    assert job_state["results"]["commit_sha"] == expected_sha
    assert job_state["results"]["dependencies_count"] == 3
    assert job_state["results"]["files_analyzed"] >= 2

    # Run scheduled review after temp workspace cleanup -> must succeed using persisted snapshot
    db = SessionLocal()
    try:
        assessment = asyncio.run(execute_project_review(project_id=project_id, trigger_type="scheduled", db_session=db))
        assert assessment.status == "completed"
        assert assessment.commit_sha == expected_sha
        assert assessment.files_analyzed >= 2
        assert assessment.lines_of_code > 0
    finally:
        db.close()


def test_failed_remote_download_transitions_to_failed_never_completed():
    headers, org_id = _auth_headers()
    _grant_enterprise_for_multi_project_test(org_id)

    proj = client.post("/api/v1/projects", json={"name": f"Fail Sync {uuid.uuid4().hex[:6]}"}, headers=headers).json()
    project_id = proj["id"]

    client.post(
        "/api/v1/repositories/connect",
        json={
            "project_id": project_id,
            "provider": "github",
            "repo_url": "https://github.com/gt-innox/nonexistent-private-repo",
            "branch": "main",
        },
        headers=headers,
    )

    async def mock_404_get(self_client, url: str, headers: dict = None, **kwargs):
        req = httpx.Request("GET", url)
        return httpx.Response(404, json={"message": "Not Found"}, request=req)

    job_id = ingestion_job_manager.create_job(project_id=project_id, org_id=org_id, provider="github", branch="main")
    with patch.object(httpx.AsyncClient, "get", new=mock_404_get), patch.object(
        RepositoryIngestionService, "validate_repository_url", side_effect=lambda u: u
    ):
        asyncio.run(
            execute_async_ingestion(
                job_id=job_id,
                project_id=project_id,
                org_id=org_id,
                repo_url="https://github.com/gt-innox/nonexistent-private-repo",
                branch="main",
                provider="github",
            )
        )

    job_state = ingestion_job_manager.get_job(job_id, org_id=org_id)
    assert job_state["sync_state"] == SYNC_STATE_FAILED
    assert job_state["status"] == "failed"
    assert "404" in (job_state["error"] or "")

    db = SessionLocal()
    try:
        conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
        assert conn.status == "failed"
        assert conn.last_sync_status == SYNC_STATE_FAILED
        run = db.query(RepositoryIngestionRun).filter(RepositoryIngestionRun.id == job_id).first()
        assert run.status == SYNC_STATE_FAILED
        snaps = db.query(RepositoryAnalysisSnapshot).filter(RepositoryAnalysisSnapshot.project_id == project_id).all()
        assert len(snaps) == 0
    finally:
        db.close()


def test_ssrf_redirect_and_archive_symlink_bomb_protections(tmp_path):
    # 1. CGNAT, IPv4-mapped IPv6, embedded credentials, and internal suffixes blocked
    for bad_url in [
        "http://100.64.0.5/repo.git",
        "http://[::ffff:127.0.0.1]/repo.git",
        "https://user:ghp_secret@github.com/org/repo.git",
        "http://metadata.internal/repo.git",
    ]:
        ok, _ = RepositoryIngestionService.validate_repo_url(bad_url)
        assert ok is False, f"Expected SSRF block for {bad_url}"

    # 2. Malicious HTTP 302 redirect to cloud metadata IP is blocked mid-flight
    async def mock_evil_redirect(self_client, url: str, headers: dict = None, **kwargs):
        req = httpx.Request("GET", url)
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"}, request=req)

    svc = RepositoryIngestionService()
    with patch.object(httpx.AsyncClient, "get", new=mock_evil_redirect):
        with pytest.raises(UnsafeRepositoryURLError):
            asyncio.run(svc.ingest_repository(repo_url="https://github.com/org/repo", branch="main", provider="github"))

    # 3. Symlink entry inside ZIP archive is rejected
    sym_buf = io.BytesIO()
    with zipfile.ZipFile(sym_buf, "w") as zf:
        zi = zipfile.ZipInfo("evil_link.py")
        zi.create_system = 3  # Unix
        zi.external_attr = (0o120777) << 16  # S_IFLNK
        zf.writestr(zi, "/etc/shadow")

    with pytest.raises(ArchiveSecurityError, match="Symbolic links"):
        RepositoryIngestionService.extract_zip_repository_safely(sym_buf.getvalue(), str(tmp_path / "sym"))

    # 4. Decompression bomb (>50x compression ratio exceeding single-file cap) is rejected
    bomb_buf = io.BytesIO()
    with zipfile.ZipFile(bomb_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("zero_bomb.bin", b"\x00" * (6 * 1024 * 1024))  # 6 MB of zeros compresses to ~6 KB (~1000x)

    with pytest.raises(ArchiveSecurityError, match="bomb"):
        RepositoryIngestionService.extract_zip_repository_safely(bomb_buf.getvalue(), str(tmp_path / "bomb"))


def test_code_findings_analyze_never_leaks_host_directory_and_bitbucket_oauth_redirect_uri():
    # Bitbucket OAuth URL includes redirect_uri
    bb = BitbucketService(client_id="cid", client_secret="csec")
    auth_url = bb.get_authorization_url("https://app.techdebt.ai/oauth/bb", "st_1")
    assert "redirect_uri=https%3A%2F%2Fapp.techdebt.ai%2Foauth%2Fbb" in auth_url

    # Unsynced project analyze endpoint returns 0 files, never scanning "."
    headers, org_id = _auth_headers()
    _grant_enterprise_for_multi_project_test(org_id)
    proj = client.post("/api/v1/projects", json={"name": f"Empty Safe {uuid.uuid4().hex[:6]}"}, headers=headers).json()
    res = client.post(f"/api/v1/code-findings/project/{proj['id']}/analyze", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "no_source_available"
    assert body["files_analyzed"] == 0
    assert body["hotspots"] == []
