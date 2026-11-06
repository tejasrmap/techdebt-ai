import os
import shutil
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.all_models import Project, User, RepositoryConnection, ProjectTechnology, Technology
from app.services.auth_service import get_current_user, require_roles
from app.services.repository_ingestion_service import (
    RepositoryIngestionService, UnsafeRepositoryURLError, ArchiveSecurityError,
    ingestion_job_manager, execute_async_ingestion
)
from app.services.parsers.dependency_parser import DependencyParser
from app.services.github_app_service import GitHubAppService, GitHubAppError
from app.services.gitlab_service import GitLabService, GitLabIntegrationError
from app.services.bitbucket_service import BitbucketService, BitbucketIntegrationError

router = APIRouter(prefix="/repositories", tags=["Repositories"])
github_app = GitHubAppService()
gitlab_service = GitLabService()
bitbucket_service = BitbucketService()

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

@router.get("/github/config")
def get_github_app_config(current_user: User = Depends(get_current_user)):
    """Retrieve public configuration status of GitHub App integration."""
    return {
        "is_configured": github_app.is_configured,
        "app_id": github_app.app_id or "",
        "client_id": github_app.client_id or "",
        "install_url": f"https://github.com/apps/{os.getenv('GITHUB_APP_SLUG', 'techdebt-ai')}/installations/new" if github_app.is_configured else None
    }

@router.get("/github/installations/{installation_id}/repositories")
def list_github_repositories(
    installation_id: str,
    current_user: User = Depends(get_current_user)
):
    """List repositories accessible to the GitHub App installation."""
    if not github_app.is_configured:
        raise HTTPException(
            status_code=503,
            detail="GitHub App integration is not configured on this instance. Please configure GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY."
        )
    try:
        repos = github_app.list_installation_repositories(installation_id)
        return {"repositories": repos}
    except GitHubAppError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/github/repositories/{owner}/{repo}/branches")
def list_github_repo_branches(
    owner: str,
    repo: str,
    installation_id: Optional[str] = None,
    token: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """List branches for a GitHub repository."""
    try:
        branches = github_app.list_repository_branches(f"{owner}/{repo}", installation_id=installation_id, token=token)
        return {"branches": branches}
    except GitHubAppError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/github/disconnect/{installation_id}")
def disconnect_github_installation(
    installation_id: str,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager"]))
):
    """Disconnect and revoke cached GitHub App installation credentials."""
    github_app.revoke_installation(installation_id)
    return {"message": "GitHub App installation disconnected successfully"}

class GitLabAuthUrlRequest(BaseModel):
    redirect_uri: str
    state: Optional[str] = "techdebt-gitlab-auth"

class GitLabTokenExchangeRequest(BaseModel):
    code: str
    redirect_uri: str

@router.get("/gitlab/config")
def get_gitlab_config(current_user: User = Depends(get_current_user)):
    """Retrieve public configuration status of GitLab integration."""
    return {
        "is_configured": gitlab_service.is_configured,
        "gitlab_url": gitlab_service.gitlab_url
    }

@router.post("/gitlab/authorize-url")
def get_gitlab_authorize_url(
    payload: GitLabAuthUrlRequest,
    current_user: User = Depends(get_current_user)
):
    """Generate OAuth authorization URL for GitLab connection."""
    if not gitlab_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="GitLab integration is not configured. Missing GITLAB_CLIENT_ID or GITLAB_CLIENT_SECRET."
        )
    try:
        url = gitlab_service.get_authorization_url(payload.redirect_uri, payload.state or "techdebt-gitlab-auth")
        return {"authorization_url": url}
    except GitLabIntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/gitlab/token")
def exchange_gitlab_token(
    payload: GitLabTokenExchangeRequest,
    current_user: User = Depends(get_current_user)
):
    """Exchange authorization code for GitLab OAuth token."""
    if not gitlab_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="GitLab integration is not configured."
        )
    try:
        data = gitlab_service.exchange_code_for_token(payload.code, payload.redirect_uri)
        return data
    except GitLabIntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/gitlab/projects")
def list_gitlab_projects(
    token: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """List projects accessible to the authenticated GitLab user."""
    if not token or not token.strip():
        raise HTTPException(status_code=400, detail="GitLab access token is required")
    try:
        projects = gitlab_service.list_user_projects(token)
        return {"projects": projects}
    except GitLabIntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/gitlab/projects/{gitlab_project_id}/branches")
def list_gitlab_project_branches(
    gitlab_project_id: str,
    token: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """List branches for a specific GitLab project."""
    if not token or not token.strip():
        raise HTTPException(status_code=400, detail="GitLab access token is required")
    try:
        branches = gitlab_service.list_project_branches(gitlab_project_id, token)
        return {"branches": branches}
    except GitLabIntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))

class BitbucketAuthUrlRequest(BaseModel):
    redirect_uri: str
    state: Optional[str] = "techdebt-bitbucket-auth"

class BitbucketTokenExchangeRequest(BaseModel):
    code: str
    redirect_uri: str

@router.get("/bitbucket/config")
def get_bitbucket_config(current_user: User = Depends(get_current_user)):
    """Retrieve public configuration status of Bitbucket integration."""
    return {
        "is_configured": bitbucket_service.is_configured
    }

@router.post("/bitbucket/authorize-url")
def get_bitbucket_authorize_url(
    payload: BitbucketAuthUrlRequest,
    current_user: User = Depends(get_current_user)
):
    """Generate OAuth authorization URL for Bitbucket connection."""
    if not bitbucket_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Bitbucket integration is not configured. Missing BITBUCKET_CLIENT_ID or BITBUCKET_CLIENT_SECRET."
        )
    try:
        url = bitbucket_service.get_authorization_url(payload.redirect_uri, payload.state or "techdebt-bitbucket-auth")
        return {"authorization_url": url}
    except BitbucketIntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/bitbucket/token")
def exchange_bitbucket_token(
    payload: BitbucketTokenExchangeRequest,
    current_user: User = Depends(get_current_user)
):
    """Exchange authorization code for Bitbucket OAuth token."""
    if not bitbucket_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Bitbucket integration is not configured."
        )
    try:
        data = bitbucket_service.exchange_code_for_token(payload.code, payload.redirect_uri)
        return data
    except BitbucketIntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/bitbucket/repositories")
def list_bitbucket_repositories(
    token: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """List repositories accessible to the authenticated Bitbucket user."""
    if not token or not token.strip():
        raise HTTPException(status_code=400, detail="Bitbucket access token is required")
    try:
        repos = bitbucket_service.list_repositories(token)
        return {"repositories": repos}
    except BitbucketIntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/bitbucket/repositories/{workspace}/{repo_slug}/branches")
def list_bitbucket_branches(
    workspace: str,
    repo_slug: str,
    token: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """List branches for a specific Bitbucket repository."""
    if not token or not token.strip():
        raise HTTPException(status_code=400, detail="Bitbucket access token is required")
    try:
        branches = bitbucket_service.list_repository_branches(workspace, repo_slug, token)
        return {"branches": branches}
    except BitbucketIntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))

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

class AsyncSyncRequest(BaseModel):
    branch: Optional[str] = None
    auth_token: Optional[str] = None

@router.post("/{project_id}/sync-async")
async def trigger_async_sync(
    project_id: str,
    background_tasks: BackgroundTasks,
    payload: Optional[AsyncSyncRequest] = None,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager", "Developer"])),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
    if not conn or not conn.repo_url:
        raise HTTPException(status_code=400, detail="No repository configured for this project. Connect a repository first.")

    branch = (payload and payload.branch) or conn.selected_branch or "main"
    auth_token = payload and payload.auth_token

    try:
        job_id = ingestion_job_manager.create_job(
            project_id=project_id,
            org_id=current_user.org_id,
            provider=conn.provider
        )
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))

    conn.status = "syncing"
    conn.last_sync_status = "in_progress"
    db.commit()

    background_tasks.add_task(
        execute_async_ingestion,
        job_id=job_id,
        project_id=project_id,
        org_id=current_user.org_id,
        repo_url=conn.repo_url,
        auth_token=auth_token,
        branch=branch,
        provider=conn.provider
    )

    return {
        "message": "Repository synchronization initiated in background",
        "job_id": job_id,
        "status": "pending",
        "progress": 0
    }

@router.get("/jobs/{job_id}")
def get_ingestion_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """Poll asynchronous repository ingestion progress and status."""
    job = ingestion_job_manager.get_job(job_id, org_id=current_user.org_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return job

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
