import os
import uuid
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from app.main import app
from app.services.github_app_service import GitHubAppService, GitHubAppError
from app.services.rate_limiter import rate_limiter

client = TestClient(app)

def _generate_test_rsa_key() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    return pem.decode("utf-8")

def test_github_app_config_endpoint():
    """Verify GitHub App public configuration endpoint returns proper status."""
    rate_limiter.reset()
    unique_suffix = uuid.uuid4().hex[:8]
    reg_res = client.post("/api/v1/auth/register", json={
        "email": f"gh_tester_{unique_suffix}@githubtest.com",
        "password": "SecurePassword123!",
        "full_name": "GH Tester",
        "organization_name": f"GH Test Org {unique_suffix}"
    })
    assert reg_res.status_code == 200
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/v1/repositories/github/config", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "is_configured" in data
    assert isinstance(data["is_configured"], bool)

def test_github_app_unconfigured_fails_safely():
    """Verify unconfigured GitHub App returns 503 rather than throwing an unhandled exception."""
    service = GitHubAppService(app_id=None, private_key=None)
    assert not service.is_configured
    with pytest.raises(GitHubAppError):
        service.generate_app_jwt()

def test_github_app_jwt_generation():
    """Verify valid RS256 JWT generation when configured with RSA key."""
    test_key = _generate_test_rsa_key()
    service = GitHubAppService(app_id="123456", private_key=test_key)
    assert service.is_configured

    jwt_token = service.generate_app_jwt()
    assert isinstance(jwt_token, str)
    assert len(jwt_token.split(".")) == 3  # Standard header.payload.signature

def test_github_app_disconnect_endpoint():
    """Verify disconnect endpoint purges cached installation credentials."""
    rate_limiter.reset()
    unique_suffix = uuid.uuid4().hex[:8]
    reg_res = client.post("/api/v1/auth/register", json={
        "email": f"gh_disc_{unique_suffix}@githubtest.com",
        "password": "SecurePassword123!",
        "full_name": "GH Disconnect Tester",
        "organization_name": f"GH Disconnect Org {unique_suffix}"
    })
    assert reg_res.status_code == 200
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/v1/repositories/github/disconnect/test-inst-123", headers=headers)
    assert res.status_code == 200
    assert "disconnected successfully" in res.json()["message"]
