import hashlib
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.all_models import User, AuditLog
from app.services.rate_limiter import rate_limiter

client = TestClient(app)

def test_registration_and_email_verification_lifecycle():
    """Verify registration, initial unverified status, and successful verification."""
    rate_limiter.reset()
    reg_email = f"lifecycle_user_{datetime.utcnow().timestamp()}@example.com"
    reg_res = client.post("/api/v1/auth/register", json={
        "email": reg_email,
        "password": "SecurePassword123!",
        "full_name": "Lifecycle Test User",
        "organization_name": f"Lifecycle Org {datetime.utcnow().timestamp()}"
    })
    assert reg_res.status_code == 200
    user_data = reg_res.json()["user"]
    assert user_data["is_verified"] is False
    token = reg_res.json()["access_token"]

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == reg_email).first()
        assert user is not None
        assert user.is_verified is False
        assert user.verification_token is not None

        # Verify resend verification endpoint does not leak token
        resend_res = client.post(
            "/api/v1/auth/resend-verification",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resend_res.status_code == 200
        assert "dispatched" in resend_res.json()["message"]
        assert "token" not in resend_res.json()

        # Simulate raw token verification
        raw_token = "verification_raw_token_xyz_1234567890"
        user.verification_token = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        user.verification_token_expires_at = datetime.utcnow() + timedelta(hours=24)
        db.commit()

        # Verify email using valid token
        verify_res = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
        assert verify_res.status_code == 200
        assert verify_res.json()["is_verified"] is True

        # Ensure DB status is updated and token cleared (single-use)
        db.refresh(user)
        assert user.is_verified is True
        assert user.verification_token is None

        # Re-attempting verification with same token fails
        reuse_res = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
        assert reuse_res.status_code == 400
        assert "Invalid or expired" in reuse_res.json()["detail"]

        # Calling resend when already verified returns appropriate status
        resend_again = client.post(
            "/api/v1/auth/resend-verification",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resend_again.status_code == 200
        assert resend_again.json()["is_verified"] is True
    finally:
        db.close()

def test_change_password_workflow():
    """Verify change-password security checks: current pwd, min length, identical rejection."""
    rate_limiter.reset()
    user_email = f"pwd_change_{datetime.utcnow().timestamp()}@example.com"
    reg_res = client.post("/api/v1/auth/register", json={
        "email": user_email,
        "password": "InitialPassword123!",
        "full_name": "Password Change User",
        "organization_name": f"PwdChange Org {datetime.utcnow().timestamp()}"
    })
    assert reg_res.status_code == 200
    token = reg_res.json()["access_token"]

    # 1. Incorrect current password fails
    bad_curr = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "WrongPassword123!", "new_password": "BrandNewPassword123!"}
    )
    assert bad_curr.status_code == 400
    assert "Incorrect current password" in bad_curr.json()["detail"]

    # 2. Identical new password fails
    ident = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "InitialPassword123!", "new_password": "InitialPassword123!"}
    )
    assert ident.status_code == 400
    assert "identical" in ident.json()["detail"]

    # 3. Successful password change
    good_change = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "InitialPassword123!", "new_password": "UpdatedPassword2026!"}
    )
    assert good_change.status_code == 200
    assert "successfully" in good_change.json()["message"]

    # 4. Old password cannot be used to login
    bad_login = client.post("/api/v1/auth/login", json={
        "email": user_email,
        "password": "InitialPassword123!"
    })
    assert bad_login.status_code == 401

    # 5. New password logs in successfully
    good_login = client.post("/api/v1/auth/login", json={
        "email": user_email,
        "password": "UpdatedPassword2026!"
    })
    assert good_login.status_code == 200
