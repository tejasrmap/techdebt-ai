import re
import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from app.database import get_db
from app.models.all_models import Technology, ProjectTechnology, Project, User, Assessment, TechnologyScore, AuditLog
from app.schemas.schemas import TechnologyCreate, TechnologyResponse, DependencyImportRequest
from app.services.auth_service import get_current_user, require_roles
from app.services.parsers.dependency_parser import DependencyParser
from app.services.dependency_health_service import DependencyHealthService
from app.config import settings

router = APIRouter(prefix="/technologies", tags=["Technologies"])

ALLOWED_MANIFEST_EXTENSIONS = {
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "requirements.txt", "pyproject.toml", "pipfile", "pipfile.lock",
    "pom.xml", "build.gradle", "build.gradle.kts",
    "cargo.toml", "cargo.lock", "go.mod", "go.sum",
    "composer.json", "composer.lock", "gemfile", "gemfile.lock"
}

def validate_manifest_upload(file_name: str, content: str):
    # 1. Path traversal & filename sanitization
    clean_name = os.path.basename(file_name.strip()).lower()
    if clean_name not in ALLOWED_MANIFEST_EXTENSIONS and not any(clean_name.endswith(ext) for ext in ALLOWED_MANIFEST_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{file_name}'. Allowed formats: {', '.join(sorted(ALLOWED_MANIFEST_EXTENSIONS))}"
        )

    # 2. File size limit
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE if hasattr(status, "HTTP_413_CONTENT_TOO_LARGE") else 413,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB"
        )

    # 3. Reject binary content or null bytes
    if "\x00" in content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Binary content or null bytes detected. Only valid UTF-8 text manifests are permitted."
        )

@router.get("", response_model=List[TechnologyResponse])
def get_technologies(project_id: Optional[str] = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if project_id:
        # Enforce organization ownership check on project
        project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        
        results = []
        for pt in project.project_technologies:
            tech = pt.technology
            latest_score = (
                db.query(TechnologyScore)
                .join(Assessment)
                .filter(TechnologyScore.technology_id == tech.id, Assessment.project_id == project_id)
                .order_by(Assessment.created_at.desc())
                .first()
            )
            results.append({
                "id": tech.id,
                "name": tech.name,
                "ecosystem": tech.ecosystem,
                "category": tech.category,
                "installed_version": pt.installed_version,
                "latest_stable_version": tech.latest_stable_version,
                "description": tech.description or "",
                "website_url": tech.website_url,
                "repo_url": tech.repo_url,
                "is_deprecated": tech.is_deprecated,
                "is_eol": tech.is_eol,
                "health_score": latest_score.overall_score if latest_score else None,
                "risk_classification": latest_score.risk_classification if latest_score else None
            })
        return results
    else:
        # Return organization-scoped catalog of technologies
        techs = (
            db.query(Technology)
            .join(ProjectTechnology, ProjectTechnology.technology_id == Technology.id)
            .join(Project, Project.id == ProjectTechnology.project_id)
            .filter(Project.org_id == current_user.org_id)
            .distinct()
            .all()
        )
        return [
            {
                "id": t.id,
                "name": t.name,
                "ecosystem": t.ecosystem,
                "category": t.category,
                "installed_version": "latest",
                "latest_stable_version": t.latest_stable_version,
                "description": t.description or "",
                "website_url": t.website_url,
                "repo_url": t.repo_url,
                "is_deprecated": t.is_deprecated,
                "is_eol": t.is_eol,
                "health_score": None,
                "risk_classification": None
            }
            for t in techs
        ]

@router.post("", response_model=TechnologyResponse)
def add_technology(
    req: TechnologyCreate,
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator", "Engineering Manager", "Developer"])),
    db: Session = Depends(get_db),
):
    # If project_id provided, verify organization ownership
    if req.project_id:
        project = db.query(Project).filter(Project.id == req.project_id, Project.org_id == current_user.org_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    tech_name = req.name.strip().lower()
    tech = db.query(Technology).filter(Technology.name == tech_name).first()
    if not tech:
        tech = Technology(
            name=tech_name,
            ecosystem=req.ecosystem or "npm",
            category=req.category or "Library",
            latest_stable_version=req.latest_stable_version or "unknown",
            description=req.description or ""
        )
        db.add(tech)
        db.commit()
        db.refresh(tech)

    if req.project_id:
        # Upsert link
        link = db.query(ProjectTechnology).filter(
            ProjectTechnology.project_id == req.project_id,
            ProjectTechnology.technology_id == tech.id
        ).first()

        if link:
            link.installed_version = req.installed_version or "latest"
        else:
            link = ProjectTechnology(
                project_id=req.project_id,
                technology_id=tech.id,
                installed_version=req.installed_version or "latest",
                file_source="manual"
            )
            db.add(link)
        db.commit()

    return {
        "id": tech.id,
        "name": tech.name,
        "ecosystem": tech.ecosystem,
        "category": tech.category,
        "installed_version": req.installed_version or "latest",
        "latest_stable_version": tech.latest_stable_version,
        "description": tech.description or "",
        "website_url": tech.website_url,
        "repo_url": tech.repo_url,
        "is_deprecated": tech.is_deprecated,
        "is_eol": tech.is_eol,
        "health_score": None,
        "risk_classification": None
    }

@router.post("/import")
def import_dependencies(
    req: DependencyImportRequest,
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator", "Engineering Manager", "Developer"])),
    db: Session = Depends(get_db),
):
    # 1. Enforce organization ownership check
    project = db.query(Project).filter(Project.id == req.project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    # 2. Strict file size and extension validation
    validate_manifest_upload(req.file_name, req.content)

    # 3. Parse dependencies
    parsed_deps = DependencyParser.parse(req.file_name, req.content)
    imported_count = 0

    for item in parsed_deps:
        name = item["name"].strip().lower()
        if not name:
            continue
        
        tech = db.query(Technology).filter(Technology.name == name).first()
        if not tech:
            tech = Technology(
                name=name,
                ecosystem=item.get("ecosystem", "npm"),
                category=item.get("category", "Library"),
                latest_stable_version="unknown"
            )
            db.add(tech)
            db.commit()
            db.refresh(tech)

        # Upsert link
        link = db.query(ProjectTechnology).filter(
            ProjectTechnology.project_id == project.id,
            ProjectTechnology.technology_id == tech.id
        ).first()

        if link:
            link.installed_version = item.get("installed_version", "latest")
            link.file_source = os.path.basename(req.file_name)
        else:
            link = ProjectTechnology(
                project_id=project.id,
                technology_id=tech.id,
                installed_version=item.get("installed_version", "latest"),
                file_source=os.path.basename(req.file_name),
                is_direct_dep=item.get("is_direct_dep", True)
            )
            db.add(link)
            imported_count += 1

    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="project.dependencies_imported",
        resource_type="project",
        resource_id=project.id,
        details={"file_name": req.file_name, "count": len(parsed_deps)}
    )
    db.add(audit)
    db.commit()

    return {
        "message": f"Successfully imported {len(parsed_deps)} dependencies from {os.path.basename(req.file_name)}",
        "imported_count": len(parsed_deps),
        "new_links_count": imported_count
    }

@router.delete("/{project_id}/remove/{technology_id}")
def remove_technology_from_project(
    project_id: str,
    technology_id: str,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager", "Developer"])),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")
    
    link = db.query(ProjectTechnology).filter(
        ProjectTechnology.project_id == project.id,
        ProjectTechnology.technology_id == technology_id
    ).first()
    
    if not link:
        raise HTTPException(status_code=404, detail="Technology link not found in project")

    db.delete(link)
    db.commit()
    return {"message": "Technology removed from project"}

class DependencyHealthRequest(BaseModel):
    dependencies: Optional[List[Dict[str, Any]]] = None
    manifest_content: Optional[str] = None
    file_name: Optional[str] = None

@router.get("/project/{project_id}/health")
def get_project_dependency_health(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    links = db.query(ProjectTechnology).filter(ProjectTechnology.project_id == project.id).all()
    dep_payloads = []
    for link in links:
        tech = db.query(Technology).filter(Technology.id == link.technology_id).first()
        if tech:
            dep_payloads.append({
                "name": tech.name,
                "version": link.installed_version or "latest",
                "ecosystem": tech.ecosystem or "unknown"
            })

    health_report = DependencyHealthService.evaluate_project_dependencies(dep_payloads)
    health_report["project_id"] = project.id
    health_report["project_name"] = project.name
    return health_report

@router.post("/evaluate-health")
def evaluate_dependencies_health(
    req: DependencyHealthRequest,
    current_user: User = Depends(get_current_user)
):
    dep_list: List[Dict[str, Any]] = []
    if req.manifest_content and req.file_name:
        parsed = DependencyParser.parse(req.file_name, req.manifest_content)
        for p in parsed:
            dep_list.append({
                "name": p.get("name"),
                "version": p.get("installed_version") or p.get("version", "latest"),
                "ecosystem": p.get("ecosystem", "unknown")
            })
    elif req.dependencies:
        dep_list = req.dependencies
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either dependencies list or manifest_content + file_name must be supplied"
        )

    return DependencyHealthService.evaluate_project_dependencies(dep_list)

