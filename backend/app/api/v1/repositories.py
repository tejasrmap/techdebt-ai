import os
import shutil
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.all_models import Project, User, RepositoryConnection, ProjectTechnology, Technology
from app.services.auth_service import get_current_user, require_roles
from app.services.repository_ingestion_service import (
    RepositoryIngestionService, UnsafeRepositoryURLError, ArchiveSecurityError
)
from app.services.parsers.dependency_parser import DependencyParser

router = APIRouter(prefix="/repositories", tags=["Repositories"])

class ConnectRepoRequest(BaseModel):
    project_id: str
    provider: str = "github" # github, gitlab, bitbucket, other
    repo_url: str
    branch: str = "main"
    access_token: Optional[str] = None

class RepoStatusResponse(BaseModel):
    id: str
    project_id: str
    provider: str
    repo_url: Optional[str]
    branch: str
    status: str
    commit_sha: Optional[str]
    file_count: int
    size_bytes: int
    last_synced_at: Optional[str]

@router.get("/{project_id}")
def get_repository_connection(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
    if not conn:
        return {"status": "unconnected", "project_id": project_id}

    return {
        "id": conn.id,
        "project_id": conn.project_id,
        "provider": conn.provider,
        "repo_url": conn.repo_url,
        "branch": conn.branch,
        "status": conn.status,
        "commit_sha": conn.commit_sha,
        "file_count": conn.file_count,
        "size_bytes": conn.size_bytes,
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None
    }

@router.post("/connect")
def connect_repository(
    req: ConnectRepoRequest,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager", "Developer"])),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == req.project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate SSRF
    is_safe, reason = RepositoryIngestionService.validate_repo_url(req.repo_url)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Invalid repository URL: {reason}")

    conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == req.project_id).first()
    if not conn:
        conn = RepositoryConnection(
            project_id=req.project_id,
            provider=req.provider,
            repo_url=req.repo_url,
            branch=req.branch,
            status="connected"
        )
        db.add(conn)
    else:
        conn.provider = req.provider
        conn.repo_url = req.repo_url
        conn.branch = req.branch
        conn.status = "connected"

    project.repository_url = req.repo_url
    db.commit()
    db.refresh(conn)

    return {
        "message": f"Successfully connected repository to project {project.name}",
        "repository_id": conn.id,
        "status": conn.status,
        "provider": conn.provider,
        "repo_url": conn.repo_url,
        "branch": conn.branch
    }

@router.post("/upload-zip")
async def upload_repository_zip(
    project_id: str = Form(...),
    branch: str = Form("main"),
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager", "Developer"])),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP archives are supported")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="ZIP archive exceeds 50MB maximum upload limit")

    try:
        # Ingestion pipeline with Zip-Slip defense and extraction quotas
        res = RepositoryIngestionService.process_zip_upload(content, project_id)
    except (ArchiveSecurityError, UnsafeRepositoryURLError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process archive: {str(e)}")

    # Update or create RepositoryConnection
    conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
    if not conn:
        conn = RepositoryConnection(
            project_id=project_id,
            provider="local_upload",
            repo_url=file.filename,
            branch=branch,
            status="synced",
            commit_sha=None,
            file_count=res["file_count"],
            size_bytes=res["total_size_bytes"],
            local_path=res["extracted_path"]
        )
        db.add(conn)
    else:
        # Remove old path if different
        if conn.local_path and conn.local_path != res["extracted_path"] and os.path.exists(conn.local_path):
            shutil.rmtree(conn.local_path, ignore_errors=True)
        conn.provider = "local_upload"
        conn.repo_url = file.filename
        conn.branch = branch
        conn.status = "synced"
        conn.file_count = res["file_count"]
        conn.size_bytes = res["total_size_bytes"]
        conn.local_path = res["extracted_path"]

    # Update project languages and frameworks if discovered
    detected_languages = list(res["languages"].keys())
    if detected_languages:
        project.languages = detected_languages

    # Discover and parse manifest dependencies automatically
    discovered_deps_count = 0
    parser = DependencyParser()
    for manifest_path in res.get("manifest_files", []):
        try:
            with open(manifest_path, "r", encoding="utf-8", errors="ignore") as mf:
                manifest_content = mf.read()
            filename = os.path.basename(manifest_path)
            deps = parser.parse_manifest(filename, manifest_content)
            for dep in deps:
                tech_name = dep["name"]
                ecosystem = dep.get("ecosystem", "unknown")
                version = dep.get("version", "unknown")

                # Upsert Technology
                tech = db.query(Technology).filter(Technology.name == tech_name, Technology.ecosystem == ecosystem).first()
                if not tech:
                    tech = Technology(name=tech_name, ecosystem=ecosystem, latest_stable_version="unknown")
                    db.add(tech)
                    db.flush()

                # Upsert ProjectTechnology
                pt = db.query(ProjectTechnology).filter(
                    ProjectTechnology.project_id == project_id,
                    ProjectTechnology.technology_id == tech.id
                ).first()
                if not pt:
                    pt = ProjectTechnology(project_id=project_id, technology_id=tech.id, installed_version=version)
                    db.add(pt)
                    discovered_deps_count += 1
        except Exception:
            continue

    db.commit()
    db.refresh(conn)

    return {
        "message": f"Successfully ingested repository ZIP ({res['file_count']} files, {res['total_size_bytes']} bytes)",
        "project_id": project_id,
        "languages": res["languages"],
        "manifests_found": len(res.get("manifest_files", [])),
        "dependencies_discovered": discovered_deps_count,
        "status": conn.status
    }

@router.delete("/{project_id}")
def disconnect_repository(
    project_id: str,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager"])),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="No repository connected to this project")

    if conn.local_path and os.path.exists(conn.local_path):
        shutil.rmtree(conn.local_path, ignore_errors=True)

    db.delete(conn)
    project.repository_url = None
    db.commit()

    return {"message": "Repository connection removed and workspace cleaned"}

@router.post("/webhook/{provider}")
async def handle_repo_webhook(provider: str, payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Receives CI/CD or push webhook notifications to automatically trigger assessment."""
    repo_url = payload.get("repository", {}).get("html_url") or payload.get("repository", {}).get("url")
    if not repo_url:
        return {"status": "ignored", "reason": "No repository URL in payload"}

    conn = db.query(RepositoryConnection).filter(RepositoryConnection.repo_url == repo_url).first()
    if not conn:
        return {"status": "ignored", "reason": "Repository not registered"}

    conn.status = "sync_queued"
    db.commit()
    return {"status": "accepted", "project_id": conn.project_id}
