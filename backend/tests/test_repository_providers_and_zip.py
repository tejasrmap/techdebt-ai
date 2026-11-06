import io
import zipfile
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.bitbucket_service import BitbucketService, BitbucketIntegrationError
from app.services.repository_ingestion_service import RepositoryIngestionService, ArchiveSecurityError
from app.services.rate_limiter import rate_limiter

client = TestClient(app)

def get_auth_headers():
    rate_limiter.reset()
    reg = client.post("/api/v1/auth/register", json={
        "email": "bb_tester@techdebt.ai",
        "password": "SecurePassword123!",
        "full_name": "Bitbucket Tester",
        "organization_name": "Bitbucket Org"
    })
    if reg.status_code == 200:
        token = reg.json()["access_token"]
    else:
        login = client.post("/api/v1/auth/login", json={
            "email": "bb_tester@techdebt.ai",
            "password": "SecurePassword123!"
        })
        token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_bitbucket_service_unconfigured():
    svc = BitbucketService(client_id="", client_secret="")
    assert not svc.is_configured
    with pytest.raises(BitbucketIntegrationError):
        svc.get_authorization_url("https://app.techdebt.ai/cb", "state123")

def test_bitbucket_service_configured_authorization_url():
    svc = BitbucketService(client_id="bb_client_key", client_secret="bb_secret_val")
    assert svc.is_configured
    url = svc.get_authorization_url("https://app.techdebt.ai/callback", "state456")
    assert "https://bitbucket.org/site/oauth2/authorize?" in url
    assert "client_id=bb_client_key" in url
    assert "state=state456" in url

@patch("httpx.Client.post")
def test_bitbucket_service_exchange_token(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"access_token": "bb_access_tok_123", "token_type": "bearer", "expires_in": 3600}
    )
    svc = BitbucketService(client_id="bb_key", client_secret="bb_sec")
    data = svc.exchange_code_for_token("auth_code_bb", "https://app.techdebt.ai/callback")
    assert data["access_token"] == "bb_access_tok_123"

@patch("httpx.Client.get")
def test_bitbucket_service_list_repositories_and_branches(mock_get):
    mock_get.side_effect = [
        MagicMock(
            status_code=200,
            json=lambda: {
                "values": [
                    {
                        "uuid": "{1234-5678}",
                        "full_name": "org/repo-alpha",
                        "name": "repo-alpha",
                        "is_private": True,
                        "mainbranch": {"name": "main"},
                        "links": {"html": {"href": "https://bitbucket.org/org/repo-alpha"}}
                    }
                ]
            }
        ),
        MagicMock(
            status_code=200,
            json=lambda: {"values": [{"name": "main"}, {"name": "staging"}]}
        )
    ]
    svc = BitbucketService(client_id="bb_key", client_secret="bb_sec")
    repos = svc.list_repositories("valid_token")
    assert len(repos) == 1
    assert repos[0]["name"] == "repo-alpha"

    branches = svc.list_repository_branches("org", "repo-alpha", "valid_token")
    assert branches == ["main", "staging"]

def test_bitbucket_api_endpoints():
    headers = get_auth_headers()
    res = client.get("/api/v1/repositories/bitbucket/config", headers=headers)
    assert res.status_code == 200
    assert "is_configured" in res.json()

    res_no_tok = client.get("/api/v1/repositories/bitbucket/repositories", headers=headers)
    assert res_no_tok.status_code == 400

def test_zip_upload_security_zip_slip_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0:root:/root:/bin/bash")
    bad_zip_bytes = buf.getvalue()

    with pytest.raises(ArchiveSecurityError) as exc_info:
        RepositoryIngestionService.extract_zip_repository_safely(bad_zip_bytes, "target_dummy")
    assert "Zip-Slip" in str(exc_info.value) or "traversal" in str(exc_info.value)

def test_zip_upload_security_corrupted_archive_rejected():
    corrupted_bytes = b"not a zip file at all, just plain text"
    with pytest.raises(ArchiveSecurityError):
        RepositoryIngestionService.extract_zip_repository_safely(corrupted_bytes, "target_dummy")

def test_zip_upload_valid_archive(tmp_path):
    target_dir = tmp_path / "valid_extract"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("index.js", "console.log('hello');")
        zf.writestr("package.json", '{"name": "test-pkg", "version": "1.0.0"}')
    zip_bytes = buf.getvalue()

    stats = RepositoryIngestionService.extract_zip_repository_safely(zip_bytes, str(target_dir))
    assert stats["file_count"] == 2
    assert (target_dir / "index.js").exists()
    assert (target_dir / "package.json").exists()
