from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.all_models import User, Team, TeamMember, Project, ProjectTeamPermission, AuditLog
from app.services.auth_service import get_current_user, require_roles
from app.services.billing_service import BillingService

router = APIRouter(prefix="/teams", tags=["Teams & RBAC"])

class CreateTeamRequest(BaseModel):
    name: str
    description: Optional[str] = None

class AddMemberRequest(BaseModel):
    user_id: str
    role: str = "member" # lead, member, viewer

class ProjectPermissionRequest(BaseModel):
    permission_level: str = "write" # read, write, admin

@router.get("")
def list_teams(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    teams = db.query(Team).filter(Team.org_id == current_user.org_id).all()
    results = []
    for t in teams:
        member_count = db.query(TeamMember).filter(TeamMember.team_id == t.id).count()
        project_count = db.query(ProjectTeamPermission).filter(ProjectTeamPermission.team_id == t.id).count()
        results.append({
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "member_count": member_count,
            "project_count": project_count,
            "created_at": t.created_at.isoformat()
        })
    return results

@router.post("", status_code=status.HTTP_201_CREATED)
def create_team(
    req: CreateTeamRequest,
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator", "Engineering Manager"])),
    db: Session = Depends(get_db)
):
    existing = db.query(Team).filter(Team.org_id == current_user.org_id, Team.name == req.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="A team with this name already exists in your organization")

    team = Team(
        org_id=current_user.org_id,
        name=req.name,
        description=req.description
    )
    db.add(team)
    db.flush()

    # Automatically add creator as team lead
    membership = TeamMember(team_id=team.id, user_id=current_user.id, role="lead")
    db.add(membership)
    db.commit()
    db.refresh(team)

    return {
        "id": team.id,
        "name": team.name,
        "description": team.description,
        "created_at": team.created_at.isoformat()
    }

@router.get("/{team_id}")
def get_team_detail(
    team_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    team = db.query(Team).filter(Team.id == team_id, Team.org_id == current_user.org_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    members = (
        db.query(TeamMember, User)
        .join(User, TeamMember.user_id == User.id)
        .filter(TeamMember.team_id == team_id)
        .all()
    )

    permissions = (
        db.query(ProjectTeamPermission, Project)
        .join(Project, ProjectTeamPermission.project_id == Project.id)
        .filter(ProjectTeamPermission.team_id == team_id)
        .all()
    )

    return {
        "id": team.id,
        "name": team.name,
        "description": team.description,
        "members": [
            {
                "user_id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "team_role": tm.role,
                "joined_at": tm.created_at.isoformat() if tm.created_at else None
            }
            for tm, u in members
        ],
        "assigned_projects": [
            {
                "project_id": p.id,
                "name": p.name,
                "permission_level": ptp.permission
            }
            for ptp, p in permissions
        ]
    }

@router.post("/{team_id}/members")
def add_team_member(
    team_id: str,
    req: AddMemberRequest,
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator", "Engineering Manager"])),
    db: Session = Depends(get_db)
):
    team = db.query(Team).filter(Team.id == team_id, Team.org_id == current_user.org_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    user = db.query(User).filter(User.id == req.user_id, User.org_id == current_user.org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found in organization")

    # User is already an organization member; verify org is not over seat quota without counting an extra seat
    allowed, limit, current = BillingService.check_entitlement(
        db, current_user.org_id, "team_members", additional_quantity=0
    )
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Team member limit reached ({current}/{limit}). Please upgrade your subscription."
        )

    existing_mem = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == req.user_id).first()
    if existing_mem:
        existing_mem.role = req.role
    else:
        mem = TeamMember(team_id=team_id, user_id=req.user_id, role=req.role)
        db.add(mem)

    db.commit()
    return {"message": "Team member updated successfully"}

@router.delete("/{team_id}/members/{user_id}")
def remove_team_member(
    team_id: str,
    user_id: str,
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator", "Engineering Manager"])),
    db: Session = Depends(get_db)
):
    team = db.query(Team).filter(Team.id == team_id, Team.org_id == current_user.org_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    mem = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id).first()
    if not mem:
        raise HTTPException(status_code=404, detail="Member not in this team")

    db.delete(mem)
    db.commit()
    return {"message": "Member removed from team"}

@router.post("/{team_id}/projects/{project_id}")
def assign_project_to_team(
    team_id: str,
    project_id: str,
    req: ProjectPermissionRequest,
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator", "Engineering Manager"])),
    db: Session = Depends(get_db)
):
    team = db.query(Team).filter(Team.id == team_id, Team.org_id == current_user.org_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    perm = db.query(ProjectTeamPermission).filter(
        ProjectTeamPermission.team_id == team_id,
        ProjectTeamPermission.project_id == project_id
    ).first()

    if not perm:
        perm = ProjectTeamPermission(
            team_id=team_id,
            project_id=project_id,
            permission=req.permission_level
        )
        db.add(perm)
    else:
        perm.permission = req.permission_level

    db.commit()
    return {"message": f"Assigned project {project.name} to team {team.name} with {req.permission_level} permission"}

@router.get("/{team_id}/activity")
def get_team_activity(
    team_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve activity audit trail for team memberships and project assignments."""
    team = db.query(Team).filter(Team.id == team_id, Team.org_id == current_user.org_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    logs = (
        db.query(AuditLog)
        .filter(
            AuditLog.org_id == current_user.org_id,
            or_(AuditLog.resource_id == team_id, AuditLog.action.like("team.%")),
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

