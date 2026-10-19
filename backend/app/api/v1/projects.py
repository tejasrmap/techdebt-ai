from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.all_models import Project, User, ProjectTechnology, Assessment, AuditLog
from app.schemas.schemas import ProjectCreate, ProjectUpdate, ProjectResponse
from app.services.auth_service import get_current_user, require_roles

router = APIRouter(prefix="/projects", tags=["Projects"])

@router.get("", response_model=List[ProjectResponse])
def get_projects(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    projects = db.query(Project).filter(Project.org_id == current_user.org_id).order_by(Project.created_at.desc()).all()
    results = []
    for p in projects:
        tech_count = db.query(ProjectTechnology).filter(ProjectTechnology.project_id == p.id).count()
        latest_assessment = (
            db.query(Assessment)
            .filter(Assessment.project_id == p.id, Assessment.status == "completed")
            .order_by(Assessment.created_at.desc())
            .first()
        )
        # Avoid misleading 100 score for unassessed projects!
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
            "risk_classification": latest_assessment.risk_classification if latest_assessment else "Not Assessed"
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
        "risk_classification": latest_assessment.risk_classification if latest_assessment else "Not Assessed"
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
