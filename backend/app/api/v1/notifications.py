from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.all_models import User, Notification
from app.services.auth_service import get_current_user
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications & Alerts"])

@router.get("")
def list_notifications(
    unread_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve notifications for the authenticated user and organization."""
    return NotificationService.get_user_notifications(
        db=db,
        user_id=current_user.id,
        org_id=current_user.org_id,
        unread_only=unread_only
    )

@router.post("/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif or (notif.org_id and notif.org_id != current_user.org_id):
        raise HTTPException(status_code=404, detail="Notification not found")

    NotificationService.mark_as_read(db, notification_id)
    return {"message": "Notification marked as read"}

@router.post("/read-all")
def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    count = NotificationService.mark_all_read(db, user_id=current_user.id, org_id=current_user.org_id)
    return {"message": f"Marked {count} notifications as read"}

