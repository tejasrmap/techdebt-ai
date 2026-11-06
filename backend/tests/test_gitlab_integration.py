import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.gitlab_service import GitLabService, GitLabIntegrationError
from app.services.auth_service import create_access_token

from app.services.rate_limiter import rate_limiter

client = TestClient(app)

def get_auth_headers():
    rate_limiter.reset()
    reg = client.post("/api/v1/auth/register", json={
        "email": "gitlab_tester@techdebt.ai",
        "password": "SecurePassword123!",
        "full_name": "GitLab Tester",
        "organization_name": "GitLab Org"
    })
    if reg.status_code == 200:
        token = reg.json()["access_token"]
    else:
        login = client.post("/api/v1/auth/login", json={
            "email": "gitlab_tester@techdebt.ai",
            "password": "SecurePassword123!"
        })
        token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_gitlab_service_unconfigured():
    svc = GitLabService(client_id="", client_secret="", gitlab_url="")
    assert not svc.is_configured
    with pytest.raises(GitLabIntegrationError):
        svc.get_authorization_url("https://app.techdebt.ai/cb", "state123")

def test_gitlab_service_configured_authorization_url():
    svc = GitLabService(client_id="gl_client_123", client_secret="gl_secret_456", gitlab_url="https://gitlab.example.com")
    assert svc.is_configured
    url = svc.get_authorization_url("https://app.techdebt.ai/callback", "xyz789")
    assert "https://gitlab.example.com/oauth/authorize?" in url
    assert "client_id=gl_client_123" in url
    assert "redirect_uri=https%3A%2F%2Fapp.techdebt.ai%2Fcallback" in url
    assert "read_api+read_repository" in url or "read_api%20read_repository" in url

@patch("httpx.Client.post")
def test_gitlab_service_exchange_token(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"access_token": "glpat_mock_999", "token_type": "bearer", "expires_in": 7200}
    )
    svc = GitLabService(client_id="gl_id", client_secret="gl_sec")
    data = svc.exchange_code_for_token("auth_code_123", "https://app.techdebt.ai/callback")
    assert data["access_token"] == "glpat_mock_999"

@patch("httpx.Client.get")
def test_gitlab_service_list_projects_and_branches(mock_get):
    mock_get.side_effect = [
        MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "id": 101,
                    "name": "payment-gateway",
                    "path_with_namespace": "fintech/payment-gateway",
                    "visibility": "private",
                    "default_branch": "main",
                    "web_url": "https://gitlab.com/fintech/payment-gateway"
                }
            ]
        ),
        MagicMock(
            status_code=200,
            json=lambda: [{"name": "main"}, {"name": "develop"}, {"name": "feature-v3"}]
        )
    ]
    svc = GitLabService(client_id="gl_id", client_secret="gl_sec")
    projects = svc.list_user_projects("mock_token")
    assert len(projects) == 1
    assert projects[0]["name"] == "payment-gateway"
    assert projects[0]["path_with_namespace"] == "fintech/payment-gateway"

    branches = svc.list_project_branches(101, "mock_token")
    assert branches == ["main", "develop", "feature-v3"]

def test_gitlab_api_endpoints():
    headers = get_auth_headers()

    # 1. Config status
    res = client.get("/api/v1/repositories/gitlab/config", headers=headers)
    assert res.status_code == 200
    assert "is_configured" in res.json()
    assert "gitlab_url" in res.json()

    # 2. Require token for branches and projects
    res_no_tok = client.get("/api/v1/repositories/gitlab/projects", headers=headers)
    assert res_no_tok.status_code == 400

    res_no_tok_br = client.get("/api/v1/repositories/gitlab/projects/101/branches", headers=headers)
    assert res_no_tok_br.status_code == 400
