from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.all_models import (
    Organization, User, Project, Team, AuditLog, Assessment,
    RiskFinding, ProjectTechnology, Technology
)
from app.services.auth_service import get_current_user, require_roles, UserRole

router = APIRouter(prefix="/organizations", tags=["Organizations & Workspace"])

class OrganizationUpdateRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None

class OwnershipTransferRequest(BaseModel):
    new_owner_user_id: str

class RetentionPolicyRequest(BaseModel):
    retention_days: int = 90
    purge_now: bool = False

@router.get("/current")
def get_current_organization(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve metadata and resource counts for the caller's organization."""
    org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    user_count = db.query(User).filter(User.org_id == org.id).count()
    project_count = db.query(Project).filter(Project.org_id == org.id).count()
    team_count = db.query(Team).filter(Team.org_id == org.id).count()

    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "plan": org.plan,
        "member_count": user_count,
        "project_count": project_count,
        "team_count": team_count,
        "created_at": org.created_at.isoformat() if org.created_at else None,
        "updated_at": org.updated_at.isoformat() if org.updated_at else None
    }

@router.put("/current")
def update_current_organization(
    req: OrganizationUpdateRequest,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.OWNER, UserRole.ADMINISTRATOR])),
    db: Session = Depends(get_db)
):
    """Edit organization name and workspace slug."""
    org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if req.name and req.name.strip():
        clean_name = req.name.strip()
        existing = db.query(Organization).filter(
            Organization.name == clean_name,
            Organization.id != org.id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="An organization with this name already exists")
        org.name = clean_name

    if req.slug and req.slug.strip():
        clean_slug = req.slug.strip().lower()
        existing_slug = db.query(Organization).filter(
            Organization.slug == clean_slug,
            Organization.id != org.id
        ).first()
        if existing_slug:
            raise HTTPException(status_code=400, detail="This organization workspace slug is already taken")
        org.slug = clean_slug

    org.updated_at = datetime.utcnow()
    audit = AuditLog(
        user_id=current_user.id,
        org_id=org.id,
        action="organization.updated",
        resource_type="organization",
        resource_id=org.id,
        details={"name": org.name, "slug": org.slug}
    )
    db.add(audit)
    db.commit()
    db.refresh(org)

    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "plan": org.plan,
        "updated_at": org.updated_at.isoformat()
    }

@router.post("/current/transfer-ownership")
def transfer_organization_ownership(
    req: OwnershipTransferRequest,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.OWNER, UserRole.ADMINISTRATOR])),
    db: Session = Depends(get_db)
):
    """Transfer organization ownership to another active member."""
    new_owner = db.query(User).filter(
        User.id == req.new_owner_user_id,
        User.org_id == current_user.org_id,
        User.is_active == True
    ).first()
    if not new_owner:
        raise HTTPException(status_code=404, detail="Target user not found or inactive in this organization")

    if new_owner.id == current_user.id:
        raise HTTPException(status_code=400, detail="You are already the owner of this organization")

    # Demote current user to Administrator if they were Owner
    if current_user.role == UserRole.OWNER:
        current_user.role = UserRole.ADMINISTRATOR

    # Promote target user to Owner
    new_owner.role = UserRole.OWNER

    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="organization.ownership_transferred",
        resource_type="organization",
        resource_id=current_user.org_id,
        details={"previous_owner_id": current_user.id, "new_owner_id": new_owner.id}
    )
    db.add(audit)
    db.commit()

    return {
        "message": f"Organization ownership transferred to {new_owner.email}",
        "new_owner_id": new_owner.id,
        "new_owner_email": new_owner.email
    }

@router.delete("/current")
def delete_current_organization(
    confirm: bool = Query(False, description="Must be true to confirm deletion"),
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.OWNER])),
    db: Session = Depends(get_db)
):
    """Delete organization and all associated workspace resources. Requires Owner role."""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required. Pass query param confirm=true to confirm organization deletion."
        )

    org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    audit = AuditLog(
        user_id=current_user.id,
        org_id=org.id,
        action="organization.deleted",
        resource_type="organization",
        resource_id=org.id,
        details={"org_name": org.name}
    )
    db.add(audit)
    db.delete(org)
    db.commit()

    return {"message": "Organization and associated resources deleted successfully"}

@router.get("/current/audit-logs")
def get_organization_audit_logs(
    action: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.OWNER, UserRole.ADMINISTRATOR])),
    db: Session = Depends(get_db)
):
    """Retrieve audit trail of administrative and security events for this organization."""
    query = db.query(AuditLog).filter(AuditLog.org_id == current_user.org_id)
    if action:
        query = query.filter(AuditLog.action == action)

    total = query.count()
    logs = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "details": log.details,
                "created_at": log.created_at.isoformat() if log.created_at else None
            }
            for log in logs
        ]
    }

@router.get("/current/export")
def export_organization_data(
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.OWNER, UserRole.ADMINISTRATOR])),
    db: Session = Depends(get_db)
):
    """Export complete organization data package for compliance, archiving, and data portability."""
    org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    projects = db.query(Project).filter(Project.org_id == org.id).all()
    project_payloads = []
    for p in projects:
        assessments = db.query(Assessment).filter(Assessment.project_id == p.id).all()
        risks = db.query(RiskFinding).filter(RiskFinding.project_id == p.id).all()
        project_payloads.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "repository_url": p.repository_url,
            "languages": p.languages,
            "frameworks": p.frameworks,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "assessments_count": len(assessments),
            "risks_count": len(risks)
        })

    members = db.query(User).filter(User.org_id == org.id).all()
    teams = db.query(Team).filter(Team.org_id == org.id).all()

    audit = AuditLog(
        user_id=current_user.id,
        org_id=org.id,
        action="organization.data_exported",
        resource_type="organization",
        resource_id=org.id,
        details={"user_email": current_user.email}
    )
    db.add(audit)
    db.commit()

    return {
        "export_timestamp": datetime.utcnow().isoformat(),
        "organization": {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "plan": org.plan,
            "created_at": org.created_at.isoformat() if org.created_at else None
        },
        "members": [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "is_verified": u.is_verified,
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in members
        ],
        "teams": [
            {"id": t.id, "name": t.name, "description": t.description}
            for t in teams
        ],
        "projects": project_payloads
    }

@router.post("/current/retention")
def configure_data_retention(
    req: RetentionPolicyRequest,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.OWNER])),
    db: Session = Depends(get_db)
):
    """Configure data retention policy and optionally purge historical logs exceeding the retention window."""
    if req.retention_days < 30:
        raise HTTPException(status_code=400, detail="Minimum retention period is 30 days")

    purged_assessments_count = 0
    purged_audit_count = 0

    if req.purge_now:
        cutoff = datetime.utcnow() - timedelta(days=req.retention_days)
        # Purge older audit logs
        purged_audit_count = db.query(AuditLog).filter(
            AuditLog.org_id == current_user.org_id,
            AuditLog.created_at < cutoff
        ).delete(synchronize_session=False)

        db.commit()

    return {
        "message": f"Retention policy configured ({req.retention_days} days)",
        "retention_days": req.retention_days,
        "purged_audit_records": purged_audit_count
    }
