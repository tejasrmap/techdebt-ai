from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.all_models import Project, User, ProjectTechnology, Assessment, AuditLog, ProjectTeamPermission, Team, HistoricalAssessment, RiskFinding
from app.schemas.schemas import ProjectCreate, ProjectUpdate, ProjectResponse
from app.services.auth_service import get_current_user, require_roles, UserRole

router = APIRouter(prefix="/projects", tags=["Projects"])

class ProjectTeamAssignmentRequest(BaseModel):
    team_id: str
    permission_level: str = "write"  # admin, write, read

@router.get("", response_model=List[ProjectResponse])
def get_projects(
    include_archived: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Project).filter(Project.org_id == current_user.org_id)
    if not include_archived:
        query = query.filter(Project.is_archived == False)
    projects = query.order_by(Project.created_at.desc()).all()
    results = []
    for p in projects:
        tech_count = db.query(ProjectTechnology).filter(ProjectTechnology.project_id == p.id).count()
        latest_assessment = (
            db.query(Assessment)
            .filter(Assessment.project_id == p.id, Assessment.status == "completed")
            .order_by(Assessment.created_at.desc())
            .first()
        )
        results.append({
            "id": p.id,
            "org_id": p.org_id,
            "name": p.name,
            "description": p.description,
            "repository_url": p.repository_url,
            "languages": p.languages or [],
            "frameworks": p.frameworks or [],
            "owner_name": p.owner_name,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
            "last_assessment_date": p.last_assessment_date,
            "technology_count": tech_count,
            "health_score": latest_assessment.overall_health_score if latest_assessment else None,
            "risk_classification": latest_assessment.risk_classification if latest_assessment else "Not Assessed",
            "is_archived": getattr(p, "is_archived", False)
        })
    return results

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    req: ProjectCreate,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager", "Developer"])),
    db: Session = Depends(get_db)
):
    # Enforce commercial subscription entitlement for project count
    from app.services.billing_service import BillingService
    allowed, limit, current = BillingService.check_entitlement(db, current_user.org_id, "projects")
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Project limit reached for your plan ({current}/{limit}). Please upgrade your subscription to add more projects."
        )

    # Check duplicate project name within the same organization
    existing = db.query(Project).filter(
        Project.org_id == current_user.org_id,
        Project.name == req.name.strip()
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A project named '{req.name.strip()}' already exists in your organization."
        )

    project = Project(
        org_id=current_user.org_id,
        name=req.name.strip(),
        description=req.description or "",
        repository_url=req.repository_url or "",
        languages=req.languages or [],
        frameworks=req.frameworks or [],
        owner_name=req.owner_name or current_user.full_name
    )
    db.add(project)
    
    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="project.create",
        resource_type="project",
        resource_id=project.id,
        details={"name": project.name}
    )
    db.add(audit)
    db.commit()
    db.refresh(project)

    return {
        "id": project.id,
        "org_id": project.org_id,
        "name": project.name,
        "description": project.description,
        "repository_url": project.repository_url,
        "languages": project.languages or [],
        "frameworks": project.frameworks or [],
        "owner_name": project.owner_name,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "last_assessment_date": None,
        "technology_count": 0,
        "health_score": None,  # Properly unassessed
        "risk_classification": None
    }

@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")
    tech_count = db.query(ProjectTechnology).filter(ProjectTechnology.project_id == p.id).count()
    latest_assessment = (
        db.query(Assessment)
        .filter(Assessment.project_id == p.id, Assessment.status == "completed")
        .order_by(Assessment.created_at.desc())
        .first()
    )
    return {
        "id": p.id,
        "org_id": p.org_id,
        "name": p.name,
        "description": p.description,
        "repository_url": p.repository_url,
        "languages": p.languages or [],
        "frameworks": p.frameworks or [],
        "owner_name": p.owner_name,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
        "last_assessment_date": p.last_assessment_date,
        "technology_count": tech_count,
        "health_score": latest_assessment.overall_health_score if latest_assessment else None,
        "risk_classification": latest_assessment.risk_classification if latest_assessment else "Not Assessed",
        "is_archived": getattr(p, "is_archived", False)
    }

@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    req: ProjectUpdate,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager"])),
    db: Session = Depends(get_db)
):
    p = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")
    
    if req.name is not None and req.name.strip():
        # Check duplicate name
        existing = db.query(Project).filter(
            Project.org_id == current_user.org_id,
            Project.name == req.name.strip(),
            Project.id != p.id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Another project already uses this name.")
        p.name = req.name.strip()

    if req.description is not None:
        p.description = req.description
    if req.repository_url is not None:
        p.repository_url = req.repository_url
    if req.languages is not None:
        p.languages = req.languages
    if req.frameworks is not None:
        p.frameworks = req.frameworks
    if req.owner_name is not None:
        p.owner_name = req.owner_name

    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="project.update",
        resource_type="project",
        resource_id=p.id,
        details={"name": p.name}
    )
    db.add(audit)
    db.commit()
    db.refresh(p)
    return get_project(project_id, current_user, db)

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager"])),
    db: Session = Depends(get_db)
):
    p = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")
    
    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="project.delete",
        resource_type="project",
        resource_id=p.id,
        details={"name": p.name}
    )
    db.add(audit)
    db.delete(p)
    db.commit()
    return None

@router.post("/{project_id}/archive")
def archive_project(
    project_id: str,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.OWNER, UserRole.ADMINISTRATOR, UserRole.ENGINEERING_MANAGER])),
    db: Session = Depends(get_db)
):
    """Archive a project to hide it from active views without deleting historical data."""
    p = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    p.is_archived = True
    p.archived_at = datetime.utcnow()

    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="project.archived",
        resource_type="project",
        resource_id=p.id,
        details={"project_name": p.name}
    )
    db.add(audit)
    db.commit()

    return {"message": f"Project '{p.name}' archived successfully", "is_archived": True}

@router.post("/{project_id}/restore")
def restore_project(
    project_id: str,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.OWNER, UserRole.ADMINISTRATOR, UserRole.ENGINEERING_MANAGER])),
    db: Session = Depends(get_db)
):
    """Restore an archived project back to active status."""
    p = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    p.is_archived = False
    p.archived_at = None

    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="project.restored",
        resource_type="project",
        resource_id=p.id,
        details={"project_name": p.name}
    )
    db.add(audit)
    db.commit()

    return {"message": f"Project '{p.name}' restored successfully", "is_archived": False}

@router.get("/{project_id}/activity")
def get_project_activity(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve activity audit log specifically for this project."""
    p = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    logs = (
        db.query(AuditLog)
        .filter(
            AuditLog.org_id == current_user.org_id,
            (AuditLog.resource_id == project_id) | (AuditLog.resource_type == "project")
        )
        .order_by(AuditLog.created_at.desc())
        .limit(50)
        .all()
    )

    return [
        {
            "id": l.id,
            "action": l.action,
            "user_id": l.user_id,
            "details": l.details,
            "created_at": l.created_at.isoformat() if l.created_at else None
        }
        for l in logs
    ]

@router.get("/{project_id}/permissions")
def list_project_team_permissions(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List teams assigned to this project and their permission levels."""
    p = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    perms = (
        db.query(ProjectTeamPermission, Team)
        .join(Team, ProjectTeamPermission.team_id == Team.id)
        .filter(ProjectTeamPermission.project_id == project_id)
        .all()
    )

    return [
        {
            "team_id": t.id,
            "team_name": t.name,
            "permission_level": ptp.permission,
            "assigned_at": ptp.created_at.isoformat() if ptp.created_at else None
        }
        for ptp, t in perms
    ]

@router.post("/{project_id}/permissions")
def assign_team_project_permission(
    project_id: str,
    req: ProjectTeamAssignmentRequest,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.OWNER, UserRole.ADMINISTRATOR, UserRole.ENGINEERING_MANAGER])),
    db: Session = Depends(get_db)
):
    """Assign or update a team's permission on this project."""
    p = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    team = db.query(Team).filter(Team.id == req.team_id, Team.org_id == current_user.org_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found in organization")

    perm = db.query(ProjectTeamPermission).filter(
        ProjectTeamPermission.project_id == project_id,
        ProjectTeamPermission.team_id == req.team_id
    ).first()

    if perm:
        perm.permission = req.permission_level
    else:
        perm = ProjectTeamPermission(
            project_id=project_id,
            team_id=req.team_id,
            permission=req.permission_level
        )
        db.add(perm)

    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="project.permission_assigned",
        resource_type="project",
        resource_id=p.id,
        details={"team_name": team.name, "permission_level": req.permission_level}
    )
    db.add(audit)
    db.commit()

    return {"message": f"Assigned team '{team.name}' with permission '{req.permission_level}'"}

@router.delete("/{project_id}/permissions/{team_id}")
def revoke_team_project_permission(
    project_id: str,
    team_id: str,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.OWNER, UserRole.ADMINISTRATOR, UserRole.ENGINEERING_MANAGER])),
    db: Session = Depends(get_db)
):
    """Revoke a team's permission on this project."""
    p = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    perm = db.query(ProjectTeamPermission).filter(
        ProjectTeamPermission.project_id == project_id,
        ProjectTeamPermission.team_id == team_id
    ).first()
    if not perm:
        raise HTTPException(status_code=404, detail="Team does not have permission on this project")

    db.delete(perm)

    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="project.permission_revoked",
        resource_type="project",
        resource_id=p.id,
        details={"team_id": team_id}
    )
    db.add(audit)
    db.commit()

    return {"message": "Team permission revoked from project"}

@router.get("/{project_id}/debt-history")
def get_project_debt_history(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    # Fetch historical assessment snapshots
    historical = (
        db.query(HistoricalAssessment)
        .filter(HistoricalAssessment.project_id == project.id)
        .order_by(HistoricalAssessment.created_at.asc())
        .all()
    )

    timeline = []
    for h in historical:
        timeline.append({
            "id": h.id,
            "assessment_id": h.assessment_id,
            "timestamp": h.created_at,
            "health_score": h.health_score,
            "score_delta": h.score_delta,
            "risk_classification": h.risk_classification,
            "summary_of_changes": h.summary_of_changes,
            "new_risks_count": h.new_risks_count,
            "resolved_risks_count": h.resolved_risks_count
        })

    # If no historical assessments yet, synthesize from completed assessments
    if not timeline:
        completed = (
            db.query(Assessment)
            .filter(Assessment.project_id == project.id, Assessment.status == "completed")
            .order_by(Assessment.created_at.asc())
            .all()
        )
        prev_score = None
        for a in completed:
            delta = round((a.overall_health_score - prev_score), 1) if prev_score is not None else 0.0
            prev_score = a.overall_health_score
            timeline.append({
                "id": a.id,
                "assessment_id": a.id,
                "timestamp": a.created_at,
                "health_score": a.overall_health_score or 80.0,
                "score_delta": delta,
                "risk_classification": a.risk_classification,
                "summary_of_changes": a.summary or "Completed assessment cycle",
                "new_risks_count": len(a.risks),
                "resolved_risks_count": 0
            })

    # Calculate overall trajectory
    trend = "stable"
    if len(timeline) >= 2:
        first_score = timeline[0]["health_score"]
        last_score = timeline[-1]["health_score"]
        diff = last_score - first_score
        if diff > 2.0:
            trend = "improving"
        elif diff < -2.0:
            trend = "degrading"

    total_resolved = sum(t["resolved_risks_count"] for t in timeline)
    avg_velocity = round((total_resolved / len(timeline)) if timeline else 0.0, 1)

    return {
        "project_id": project.id,
        "project_name": project.name,
        "snapshots_count": len(timeline),
        "overall_trend": trend,
        "cumulative_resolved_risks": total_resolved,
        "remediation_velocity_per_cycle": avg_velocity,
        "timeline": timeline
    }

