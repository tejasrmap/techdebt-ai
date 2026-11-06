import hashlib
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.all_models import User
from app.services.auth_service import verify_password
from app.services.rate_limiter import rate_limiter

client = TestClient(app)

def test_forgot_password_does_not_expose_token():
    """Verify that forgot_password never returns reset_token in public response."""
    rate_limiter.reset()
    res = client.post("/api/v1/auth/forgot-password", json={"email": "admin@techdebt.ai"})
    assert res.status_code == 200
    data = res.json()
    assert "reset_token" not in data, "Security vulnerability: reset_token must NOT be in response"
    assert "password reset link has been dispatched" in data["message"]

def test_password_reset_stores_sha256_hash_and_resets():
    """Verify cryptographically secure token hashing, successful reset, and single-use."""
    rate_limiter.reset()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "admin@techdebt.ai").first()
        assert user is not None

        # Simulate generating a raw token
        raw_token = "secure_test_recovery_token_abcdef1234567890"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        user.reset_password_token = token_hash
        user.reset_password_token_expires_at = datetime.utcnow() + timedelta(hours=1)
        db.commit()

        # Check DB has hash, NOT raw token
        db.refresh(user)
        assert user.reset_password_token == token_hash
        assert user.reset_password_token != raw_token

        # Reset password with valid raw token
        reset_res = client.post("/api/v1/auth/reset-password", json={
            "token": raw_token,
            "new_password": "NewStrongAdminPassword2026!"
        })
        assert reset_res.status_code == 200
        assert "successfully reset" in reset_res.json()["message"]

        # Verify password in DB updated and token invalidated
        db.refresh(user)
        assert user.reset_password_token is None
        assert user.reset_password_token_expires_at is None
        assert verify_password("NewStrongAdminPassword2026!", user.hashed_password)

        # Attempt token reuse - MUST fail with 400
        reuse_res = client.post("/api/v1/auth/reset-password", json={
            "token": raw_token,
            "new_password": "AnotherPassword123!"
        })
        assert reuse_res.status_code == 400
        assert "Invalid or expired" in reuse_res.json()["detail"]

        # Restore original password for downstream tests
        from app.services.auth_service import get_password_hash
        user.hashed_password = get_password_hash("AdminPass123!")
        db.commit()
    finally:
        db.close()

def test_password_reset_expired_token():
    """Verify expired tokens are rejected."""
    rate_limiter.reset()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "admin@techdebt.ai").first()
        raw_token = "expired_test_recovery_token_9876543210zyx"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        user.reset_password_token = token_hash
        user.reset_password_token_expires_at = datetime.utcnow() - timedelta(minutes=10)
        db.commit()

        res = client.post("/api/v1/auth/reset-password", json={
            "token": raw_token,
            "new_password": "ExpiredTokenPassword123!"
        })
        assert res.status_code == 400
        assert "Invalid or expired" in res.json()["detail"]
    finally:
        db.close()

def test_password_reset_brute_force_rate_limit():
    """Verify rate limiter blocks brute-force attempts on reset endpoints."""
    rate_limiter.reset()
    for _ in range(5):
        client.post("/api/v1/auth/forgot-password", json={"email": "nonexistent@test.com"})

    # 6th attempt should be blocked with 429
    blocked_res = client.post("/api/v1/auth/forgot-password", json={"email": "nonexistent@test.com"})
    assert blocked_res.status_code == 429
    rate_limiter.reset()
