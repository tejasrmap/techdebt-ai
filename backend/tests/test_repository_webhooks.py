import hmac
import hashlib
import json
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.all_models import Project, RepositoryConnection
from app.services.rate_limiter import rate_limiter

client = TestClient(app)

def setup_test_repo(provider="github", repo_url="https://github.com/techdebt/core-engine", secret="super-secret-token"):
    rate_limiter.reset()
    reg = client.post("/api/v1/auth/register", json={
        "email": f"webhook_{uuid.uuid4().hex[:6]}@techdebt.ai",
        "password": "SecurePassword123!",
        "full_name": "Webhook Tester",
        "organization_name": f"Webhook Org {uuid.uuid4().hex[:4]}"
    }).json()
    token = reg["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create project
    p = client.post("/api/v1/projects", json={"name": f"Webhook Proj {uuid.uuid4().hex[:6]}"}, headers=headers).json()
    proj_id = p["id"]

    # Connect repo
    c = client.post("/api/v1/repositories/connect", json={
        "project_id": proj_id,
        "provider": provider,
        "repo_url": repo_url,
        "branch": "main"
    }, headers=headers).json()

    # Set webhook secret directly on DB model for testing HMAC verification
    db = SessionLocal()
    try:
        conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == proj_id).first()
        conn.webhook_secret = secret
        db.commit()
    finally:
        db.close()

    return proj_id, repo_url, secret

def test_github_webhook_ping():
    res = client.post(
        "/api/v1/repositories/webhook/github",
        json={"zen": "Design for failure."},
        headers={"X-GitHub-Event": "ping"}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "pong"

def test_github_webhook_push_with_valid_hmac():
    unique_sha = hashlib.sha1(uuid.uuid4().bytes).hexdigest()
    proj_id, repo_url, secret = setup_test_repo("github", f"https://github.com/org/repo-{uuid.uuid4().hex[:8]}")
    payload = {
        "repository": {"html_url": repo_url},
        "ref": "refs/heads/main",
        "after": unique_sha,
        "head_commit": {
            "id": unique_sha,
            "message": "fix: update production dependencies",
            "author": {"name": "Senior Dev"}
        }
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    res = client.post(
        "/api/v1/repositories/webhook/github",
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "accepted"
    assert data["branch"] == "main"
    assert data["commit_sha"] == unique_sha

def test_github_webhook_push_with_invalid_hmac():
    proj_id, repo_url, secret = setup_test_repo("github", "https://github.com/org/repo-bad-sig")
    payload = {
        "repository": {"html_url": repo_url},
        "ref": "refs/heads/main"
    }
    raw_body = json.dumps(payload).encode("utf-8")

    res = client.post(
        "/api/v1/repositories/webhook/github",
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=invalid_tampered_signature"
        }
    )
    assert res.status_code == 401
    assert "Invalid GitHub webhook" in res.json()["detail"]

def test_gitlab_webhook_push_with_token():
    gl_sha = f"gl_sha_{uuid.uuid4().hex[:12]}"
    proj_id, repo_url, secret = setup_test_repo("gitlab", f"https://gitlab.com/group/proj-{uuid.uuid4().hex[:8]}", secret="gl-secret-xyz")
    payload = {
        "project": {"web_url": repo_url},
        "ref": "refs/heads/main",
        "checkout_sha": gl_sha,
        "user_name": "GitLab Admin",
        "commits": [{"id": gl_sha, "message": "feat: enterprise dashboard"}]
    }

    # 1. Invalid token returns 401
    bad_res = client.post(
        "/api/v1/repositories/webhook/gitlab",
        json=payload,
        headers={"X-Gitlab-Token": "wrong-secret"}
    )
    assert bad_res.status_code == 401

    # 2. Valid token succeeds
    good_res = client.post(
        "/api/v1/repositories/webhook/gitlab",
        json=payload,
        headers={"X-Gitlab-Token": secret}
    )
    assert good_res.status_code == 200
    assert good_res.json()["status"] == "accepted"

def test_webhook_unmonitored_branch_ignored():
    proj_id, repo_url, secret = setup_test_repo("github", "https://github.com/org/repo-branch-test")
    payload = {
        "repository": {"html_url": repo_url},
        "ref": "refs/heads/feature-experimental",
        "after": "some_sha"
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    res = client.post(
        "/api/v1/repositories/webhook/github",
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig
        }
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"
    assert "monitored branch" in res.json()["reason"]
