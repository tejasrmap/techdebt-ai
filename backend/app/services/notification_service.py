import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.all_models import Notification, NotificationPreference, User

logger = logging.getLogger(__name__)

class NotificationService:
    """
    Commercial notification engine supporting in-app activity feeds,
    alert categories, severity levels, and user notification preferences.
    """

    @classmethod
    def create_notification(
        cls,
        db: Session,
        org_id: str,
        title: str,
        message: str,
        category: str = "assessment",  # assessment, security, billing, team, system
        severity: str = "info",        # info, warning, error, success
        link: str = "",
        user_id: Optional[str] = None,
        **kwargs
    ) -> Notification:
        """
        Creates and stores an in-app notification. If user_id is None, notification is
        broadcast to all active users within the organization.
        """
        cat = kwargs.get("type", category)
        notif = Notification(
            org_id=org_id,
            user_id=user_id,
            title=title,
            message=message,
            category=cat,
            severity=severity,
            link=link,
            is_read=False,
            created_at=datetime.utcnow()
        )
        db.add(notif)
        db.commit()
        db.refresh(notif)
        logger.info(f"Notification [{category}:{severity}] dispatched for org {org_id}: {title}")
        return notif

    @classmethod
    def get_user_notifications(
        cls,
        db: Session,
        org_id: str,
        user_id: str,
        limit: int = 50,
        unread_only: bool = False
    ) -> List[Notification]:
        """Fetches notifications for a user, including org-wide notifications."""
        query = db.query(Notification).filter(
            Notification.org_id == org_id,
            (Notification.user_id == user_id) | (Notification.user_id.is_(None))
        )
        if unread_only:
            query = query.filter(Notification.is_read.is_(False))
        return query.order_by(Notification.created_at.desc()).limit(limit).all()

    @classmethod
    def mark_as_read(cls, db: Session, org_id: str, notification_id: str, user_id: str) -> bool:
        """Marks specific notification as read."""
        notif = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.org_id == org_id
        ).first()
        if notif:
            notif.is_read = True
            db.commit()
            return True
        return False

    @classmethod
    def mark_all_as_read(cls, db: Session, org_id: str, user_id: str) -> int:
        """Marks all notifications for user as read."""
        updated = db.query(Notification).filter(
            Notification.org_id == org_id,
            (Notification.user_id == user_id) | (Notification.user_id.is_(None)),
            Notification.is_read.is_(False)
        ).update({"is_read": True}, synchronize_session=False)
        db.commit()
        return updated
