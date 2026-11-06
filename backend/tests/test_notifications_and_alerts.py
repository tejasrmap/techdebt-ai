import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import SessionLocal
from app.models.all_models import User, Organization, Notification, NotificationPreference
from app.services.notification_service import NotificationService

client = TestClient(app)

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def get_test_auth(db: Session):
    uid = uuid.uuid4().hex[:8]
    email = f"notif_{uid}@example.com"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": f"Notification User {uid}",
        "organization_name": f"Notification Org {uid}"
    })
    token = reg.json()["access_token"]
    org_id = reg.json()["user"]["org_id"]
    user_id = reg.json()["user"]["id"]
    return {"Authorization": f"Bearer {token}"}, org_id, user_id, email

def test_notification_lifecycle_and_unread_count(db: Session):
    headers, org_id, user_id, email = get_test_auth(db)

    # 1. Initially 0 unread
    resp_count = client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp_count.status_code == 200
    assert resp_count.json()["unread_count"] == 0

    # 2. Create in-app notifications
    notif1 = NotificationService.create_notification(
        db=db,
        org_id=org_id,
        user_id=user_id,
        title="Weekly Scan Complete",
        message="All services were scanned with 0 critical findings.",
        category="assessment",
        severity="success"
    )
    notif2 = NotificationService.create_notification(
        db=db,
        org_id=org_id,
        user_id=user_id,
        title="Payment Successful",
        message="Your subscription renewal was processed.",
        category="billing",
        severity="info"
    )

    # 3. Check unread count is now 2
    resp_count2 = client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp_count2.json()["unread_count"] == 2

    # 4. Mark one as read
    resp_read1 = client.post(f"/api/v1/notifications/{notif1.id}/read", headers=headers)
    assert resp_read1.status_code == 200

    resp_count3 = client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp_count3.json()["unread_count"] == 1

    # 5. Mark all as read
    resp_read_all = client.post("/api/v1/notifications/read-all", headers=headers)
    assert resp_read_all.status_code == 200
    assert resp_read_all.json()["count"] == 1

    resp_count4 = client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp_count4.json()["unread_count"] == 0

def test_notification_preferences_and_email_dispatch(db: Session):
    headers, org_id, user_id, email = get_test_auth(db)

    # 1. Get default preferences
    resp_pref = client.get("/api/v1/notifications/preferences", headers=headers)
    assert resp_pref.status_code == 200
    p = resp_pref.json()
    assert p["email_assessment_completed"] is True
    assert p["email_critical_risk"] is True

    # 2. Update preferences
    resp_upd = client.put("/api/v1/notifications/preferences", json={
        "email_weekly_digest": False,
        "email_billing_alerts": False
    }, headers=headers)
    assert resp_upd.status_code == 200
    assert resp_upd.json()["preferences"]["email_weekly_digest"] is False
    assert resp_upd.json()["preferences"]["email_billing_alerts"] is False
    assert resp_upd.json()["preferences"]["email_critical_risk"] is True

    # 3. Send test alert
    initial_email_count = len(NotificationService.dispatched_emails)
    resp_test = client.post("/api/v1/notifications/test-alert", json={
        "channel": "both",
        "title": "Critical Alert Test",
        "message": "Testing multi-channel notification engine.",
        "severity": "error"
    }, headers=headers)
    assert resp_test.status_code == 200
    assert resp_test.json()["email_dispatched"] is True
    assert len(NotificationService.dispatched_emails) > initial_email_count

    # 4. Test service methods: send_critical_risk_alert
    NotificationService.send_critical_risk_alert(
        db=db,
        org_id=org_id,
        project_name="Core Auth",
        risk_title="CVE-2026-9999 Remote Code Execution",
        severity="Critical"
    )
    last_email = NotificationService.dispatched_emails[-1]
    assert "Critical" in last_email["subject"]
    assert email == last_email["to"]

def test_notification_tenant_isolation(db: Session):
    headers_a, org_id_a, user_id_a, _ = get_test_auth(db)
    headers_b, org_id_b, user_id_b, _ = get_test_auth(db)

    # Org A notification
    notif_a = NotificationService.create_notification(
        db=db,
        org_id=org_id_a,
        user_id=user_id_a,
        title="Org A Confidential Notice",
        message="Internal memo"
    )

    # Org B cannot mark Org A's notification as read
    resp_b = client.post(f"/api/v1/notifications/{notif_a.id}/read", headers=headers_b)
    assert resp_b.status_code == 404

    # Org B list does not include Org A's notification
    resp_list_b = client.get("/api/v1/notifications", headers=headers_b)
    assert resp_list_b.status_code == 200
    notif_ids = [n["id"] for n in resp_list_b.json()]
    assert notif_a.id not in notif_ids
