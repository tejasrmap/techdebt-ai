import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.all_models import Notification, NotificationPreference, User

logger = logging.getLogger(__name__)

class NotificationService:
    """
    Commercial notification and alerting engine supporting in-app activity feeds,
    alert categories, severity levels, user notification preferences, and email dispatching.
    """

    SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "alerts@techdebt.ai")
    VENDOR_NAME = "GT InnoX LLP"

    # In-memory buffer of dispatched emails for testing / audit verification
    dispatched_emails: List[Dict[str, Any]] = []

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
    def get_unread_count(cls, db: Session, org_id: str, user_id: str) -> int:
        """Counts unread notifications for a user."""
        return db.query(Notification).filter(
            Notification.org_id == org_id,
            (Notification.user_id == user_id) | (Notification.user_id.is_(None)),
            Notification.is_read.is_(False)
        ).count()

    @classmethod
    def mark_as_read(
        cls,
        db: Session,
        notification_id: str,
        org_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> bool:
        """Marks specific notification as read."""
        query = db.query(Notification).filter(Notification.id == notification_id)
        if org_id:
            query = query.filter(Notification.org_id == org_id)
        notif = query.first()
        if notif:
            notif.is_read = True
            db.commit()
            return True
        return False

    @classmethod
    def mark_all_as_read(cls, db: Session, org_id: str, user_id: Optional[str] = None) -> int:
        """Marks all unread notifications for user/org as read."""
        query = db.query(Notification).filter(
            Notification.org_id == org_id,
            Notification.is_read.is_(False)
        )
        if user_id:
            query = query.filter((Notification.user_id == user_id) | (Notification.user_id.is_(None)))

        count = query.update({"is_read": True}, synchronize_session=False)
        db.commit()
        return count

    @classmethod
    def mark_all_read(cls, db: Session, user_id: Optional[str] = None, org_id: Optional[str] = None) -> int:
        """Alias for mark_all_as_read."""
        return cls.mark_all_as_read(db, org_id=org_id or "", user_id=user_id)

    @classmethod
    def get_or_create_preferences(cls, db: Session, user_id: str) -> NotificationPreference:
        """Retrieve or create default notification preferences for a user."""
        pref = db.query(NotificationPreference).filter(NotificationPreference.user_id == user_id).first()
        if not pref:
            pref = NotificationPreference(
                user_id=user_id,
                email_assessment_completed=True,
                email_critical_risk=True,
                email_billing_alerts=True,
                email_weekly_digest=True,
                inapp_notifications=True
            )
            db.add(pref)
            db.commit()
            db.refresh(pref)
        return pref

    @classmethod
    def update_preferences(cls, db: Session, user_id: str, updates: Dict[str, Any]) -> NotificationPreference:
        """Update notification preferences for a user."""
        pref = cls.get_or_create_preferences(db, user_id)
        for key, value in updates.items():
            if hasattr(pref, key) and key != "user_id" and key != "id":
                setattr(pref, key, bool(value))
        db.commit()
        db.refresh(pref)
        return pref

    @classmethod
    def dispatch_email(
        cls,
        to_email: str,
        subject: str,
        html_body: str,
        plain_body: str = ""
    ) -> bool:
        """
        Dispatches email notification via SMTP or captures in dispatched_emails buffer.
        """
        email_record = {
            "to": to_email,
            "subject": subject,
            "html_body": html_body,
            "plain_body": plain_body or subject,
            "timestamp": datetime.utcnow().isoformat(),
            "from": cls.SMTP_FROM
        }
        cls.dispatched_emails.append(email_record)

        if not cls.SMTP_USER or cls.SMTP_HOST in ("localhost", "127.0.0.1", ""):
            logger.info(f"[Email Sandbox] Dispatched email to {to_email}: {subject}")
            return True

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"TechDebt AI <{cls.SMTP_FROM}>"
            msg["To"] = to_email

            if plain_body:
                msg.attach(MIMEText(plain_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(cls.SMTP_HOST, cls.SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(cls.SMTP_USER, cls.SMTP_PASSWORD)
                server.sendmail(cls.SMTP_FROM, [to_email], msg.as_string())
            logger.info(f"SMTP email successfully sent to {to_email}")
            return True
        except Exception as e:
            logger.warning(f"Could not deliver email to {to_email} via SMTP: {e}")
            return False

    @classmethod
    def send_assessment_completed_notification(
        cls,
        db: Session,
        org_id: str,
        project_name: str,
        health_score: float,
        assessment_id: str
    ):
        """Dispatches in-app notification and email for assessment completion."""
        title = f"Assessment Completed: {project_name}"
        message = f"Assessment for {project_name} finished with Health Score: {health_score}/100."
        link = f"/assessments/{assessment_id}"

        cls.create_notification(
            db=db,
            org_id=org_id,
            title=title,
            message=message,
            category="assessment",
            severity="success" if health_score >= 80 else ("warning" if health_score >= 60 else "error"),
            link=link
        )

        # Notify users who opted in
        users = db.query(User).filter(User.org_id == org_id, User.is_active == True).all()
        for u in users:
            prefs = cls.get_or_create_preferences(db, u.id)
            if prefs.email_assessment_completed and u.email:
                html = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px;">
                    <h2>Assessment Completed</h2>
                    <p>Your assessment for <b>{project_name}</b> has finished.</p>
                    <p><b>Overall Health Score:</b> {health_score} / 100</p>
                    <p><a href="https://app.techdebt.ai{link}" style="background-color: #2563eb; color: white; padding: 10px 16px; text-decoration: none; border-radius: 4px;">View Full Report</a></p>
                    <hr/>
                    <small>{cls.VENDOR_NAME} — TechDebt AI</small>
                </div>
                """
                cls.dispatch_email(u.email, f"[TechDebt AI] Assessment Completed: {project_name}", html)

    @classmethod
    def send_critical_risk_alert(
        cls,
        db: Session,
        org_id: str,
        project_name: str,
        risk_title: str,
        severity: str = "Critical",
        risk_id: str = ""
    ):
        """Dispatches high-priority security alert for critical risks."""
        title = f"Alert: {severity} Risk in {project_name}"
        message = f"New {severity} risk identified: {risk_title}. Immediate remediation recommended."
        link = f"/risks/{risk_id}" if risk_id else "/risks"

        cls.create_notification(
            db=db,
            org_id=org_id,
            title=title,
            message=message,
            category="security",
            severity="error",
            link=link
        )

        users = db.query(User).filter(User.org_id == org_id, User.is_active == True).all()
        for u in users:
            prefs = cls.get_or_create_preferences(db, u.id)
            if prefs.email_critical_risk and u.email:
                html = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px;">
                    <h2 style="color: #dc2626;">Security Risk Alert: {severity}</h2>
                    <p>A new high-priority risk was detected in project <b>{project_name}</b>:</p>
                    <blockquote style="border-left: 4px solid #dc2626; padding-left: 12px; margin: 16px 0;">
                        <b>{risk_title}</b>
                    </blockquote>
                    <p><a href="https://app.techdebt.ai{link}" style="background-color: #dc2626; color: white; padding: 10px 16px; text-decoration: none; border-radius: 4px;">Review Finding</a></p>
                    <hr/>
                    <small>{cls.VENDOR_NAME} — TechDebt AI Security Engine</small>
                </div>
                """
                cls.dispatch_email(u.email, f"[ACTION REQUIRED] {severity} Risk in {project_name}: {risk_title}", html)
