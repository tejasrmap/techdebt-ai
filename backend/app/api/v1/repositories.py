import os
import shutil
import hmac
import hashlib
import secrets
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.all_models import (
    Project,
    User,
    RepositoryConnection,
    RepositoryIngestionRun,
    RepositoryAnalysisSnapshot,
    WebhookDeliveryEvent,
)
from app.services.auth_service import get_current_user, require_roles
from app.services.crypto_service import encrypt_credential, decrypt_credential
import app.services.repository_ingestion_service as repo_ingestion_module
from app.services.repository_ingestion_service import (
    RepositoryIngestionService,
    UnsafeRepositoryURLError,
    ArchiveSecurityError,
    SYNC_STATE_QUEUED,
    SYNC_STATE_ANALYSING,
    SYNC_STATE_PERSISTING,
    SYNC_STATE_COMPLETED,
    SYNC_STATE_FAILED,
    SYNC_STATE_CANCELLED,
    persist_ingestion_snapshot,
    ingestion_job_manager,
)
from app.services.github_app_service import GitHubAppService, GitHubAppError
from app.services.gitlab_service import GitLabService, GitLabIntegrationError
from app.services.bitbucket_service import BitbucketService, BitbucketIntegrationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repositories", tags=["Repositories"])
github_app = GitHubAppService()
gitlab_service = GitLabService()
bitbucket_service = BitbucketService()

MUTATING_REPO_ROLES = ["SuperAdmin", "Owner", "Administrator", "Engineering Manager", "Developer"]
ADMIN_REPO_ROLES = ["SuperAdmin", "Owner", "Administrator", "Engineering Manager"]


class ConnectRepoRequest(BaseModel):
    project_id: str
    provider: str = "github"  # github, gitlab, bitbucket, other
    repo_url: str
    branch: str = "main"
    access_token: Optional[str] = None
    installation_id: Optional[str] = None
    webhook_secret: Optional[str] = None


class RepoStatusResponse(BaseModel):
    id: str
    project_id: str
    provider: str
    repo_url: Optional[str]
    branch: str
    status: str
    sync_state: Optional[str] = None
    commit_sha: Optional[str]
    file_count: int
    size_bytes: int
    last_synced_at: Optional[str]


def _resolve_webhook_secret(conn: RepositoryConnection) -> str:
    raw = (conn.webhook_secret or "").strip()
    if not raw:
        return ""
    if raw.startswith("gAAAAA"):
        decrypted = decrypt_credential(raw, safe_fallback=True)
        if decrypted:
            return decrypted
    return raw


@router.get("/github/config")
def get_github_app_config(current_user: User = Depends(get_current_user)):
    """Retrieve public configuration status of GitHub App integration."""
    return {
        "is_configured": github_app.is_configured,
        "app_id": github_app.app_id or "",
        "client_id": github_app.client_id or "",
        "install_url": (
            f"https://github.com/apps/{os.getenv('GITHUB_APP_SLUG', 'techdebt-ai')}/installations/new"
            if github_app.is_configured
            else None
        ),
    }


@router.get("/github/installations/{installation_id}/repositories")
def list_github_repositories(
    installation_id: str,
    current_user: User = Depends(get_current_user),
):
    """List repositories accessible to the GitHub App installation."""
    if not github_app.is_configured:
        raise HTTPException(
            status_code=503,
            detail="GitHub App integration is not configured on this instance. Please configure GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY.",
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
    current_user: User = Depends(get_current_user),
):
    """List branches for a GitHub repository."""
    try:
        branches = github_app.list_repository_branches(
            f"{owner}/{repo}", installation_id=installation_id, token=token
        )
        return {"branches": branches}
    except GitHubAppError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/github/disconnect/{installation_id}")
def disconnect_github_installation(
    installation_id: str,
    current_user: User = Depends(require_roles(ADMIN_REPO_ROLES)),
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
        "gitlab_url": gitlab_service.gitlab_url,
    }


@router.post("/gitlab/authorize-url")
def get_gitlab_authorize_url(
    payload: GitLabAuthUrlRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate OAuth authorization URL for GitLab connection."""
    if not gitlab_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="GitLab integration is not configured. Missing GITLAB_CLIENT_ID or GITLAB_CLIENT_SECRET.",
        )
    try:
        url = gitlab_service.get_authorization_url(payload.redirect_uri, payload.state or "techdebt-gitlab-auth")
        return {"authorization_url": url}
    except GitLabIntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/gitlab/token")
def exchange_gitlab_token(
    payload: GitLabTokenExchangeRequest,
    current_user: User = Depends(get_current_user),
):
    """Exchange authorization code for GitLab OAuth token."""
    if not gitlab_service.is_configured:
        raise HTTPException(status_code=503, detail="GitLab integration is not configured.")
    try:
        data = gitlab_service.exchange_code_for_token(payload.code, payload.redirect_uri)
        return data
    except GitLabIntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/gitlab/projects")
def list_gitlab_projects(
    token: Optional[str] = None,
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    return {"is_configured": bitbucket_service.is_configured}


@router.post("/bitbucket/authorize-url")
def get_bitbucket_authorize_url(
    payload: BitbucketAuthUrlRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate OAuth authorization URL for Bitbucket connection."""
    if not bitbucket_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Bitbucket integration is not configured. Missing BITBUCKET_CLIENT_ID or BITBUCKET_CLIENT_SECRET.",
        )
    try:
        url = bitbucket_service.get_authorization_url(payload.redirect_uri, payload.state or "techdebt-bitbucket-auth")
        return {"authorization_url": url}
    except BitbucketIntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bitbucket/token")
def exchange_bitbucket_token(
    payload: BitbucketTokenExchangeRequest,
    current_user: User = Depends(get_current_user),
):
    """Exchange authorization code for Bitbucket OAuth token."""
    if not bitbucket_service.is_configured:
        raise HTTPException(status_code=503, detail="Bitbucket integration is not configured.")
    try:
        data = bitbucket_service.exchange_code_for_token(payload.code, payload.redirect_uri)
        return data
    except BitbucketIntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bitbucket/repositories")
def list_bitbucket_repositories(
    token: Optional[str] = None,
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
    if not conn:
        return {"status": "unconnected", "sync_state": None, "project_id": project_id}

    latest_snapshot = (
        db.query(RepositoryAnalysisSnapshot)
        .filter(RepositoryAnalysisSnapshot.project_id == project_id)
        .order_by(RepositoryAnalysisSnapshot.created_at.desc())
        .first()
    )

    return {
        "id": conn.id,
        "project_id": conn.project_id,
        "provider": conn.provider,
        "repo_name": conn.repo_name,
        "repo_url": conn.repo_url,
        "branch": conn.selected_branch or conn.branch or "main",
        "status": conn.status,
        "sync_state": conn.last_sync_status,
        "commit_sha": conn.commit_sha,
        "commit_message": conn.commit_message,
        "commit_author": conn.commit_author,
        "file_count": conn.file_count or 0,
        "size_bytes": conn.size_bytes or 0,
        "has_credentials": bool(conn.encrypted_access_token or (conn.metadata_json or {}).get("installation_id")),
        "webhook_configured": bool(conn.webhook_secret),
        "latest_snapshot_id": latest_snapshot.id if latest_snapshot else None,
        "lines_of_code": latest_snapshot.lines_of_code if latest_snapshot else 0,
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
    }


@router.get("/{project_id}/snapshots")
def list_repository_snapshots(
    project_id: str,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List durable repository analysis snapshots for a project."""
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    snapshots = (
        db.query(RepositoryAnalysisSnapshot)
        .filter(RepositoryAnalysisSnapshot.project_id == project_id)
        .order_by(RepositoryAnalysisSnapshot.created_at.desc())
        .limit(min(100, max(1, limit)))
        .all()
    )
    return {
        "project_id": project_id,
        "snapshots": [
            {
                "id": s.id,
                "provider": s.provider,
                "branch": s.branch,
                "commit_sha": s.commit_sha,
                "commit_message": s.commit_message,
                "commit_author": s.commit_author,
                "analyzer_version": s.analyzer_version,
                "files_examined": s.files_examined,
                "files_analyzed": s.files_analyzed,
                "files_excluded": s.files_excluded,
                "lines_of_code": s.lines_of_code,
                "maintainability_index": s.maintainability_index,
                "quality_grade": s.quality_grade,
                "dependencies_count": len(s.dependencies_json or []),
                "findings_count": len(s.code_findings_json or []),
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in snapshots
        ],
    }


@router.get("/{project_id}/ingestion-runs")
def list_repository_ingestion_runs(
    project_id: str,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List explicit repository ingestion runs and state transitions."""
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    runs = (
        db.query(RepositoryIngestionRun)
        .filter(RepositoryIngestionRun.project_id == project_id)
        .order_by(RepositoryIngestionRun.created_at.desc())
        .limit(min(100, max(1, limit)))
        .all()
    )
    return {
        "project_id": project_id,
        "runs": [
            {
                "id": r.id,
                "provider": r.provider,
                "branch": r.branch,
                "commit_sha": r.commit_sha,
                "status": r.status,
                "analyzer_version": r.analyzer_version,
                "files_examined": r.files_examined,
                "files_analyzed": r.files_analyzed,
                "files_excluded": r.files_excluded,
                "lines_of_code": r.lines_of_code,
                "dependencies_detected_count": r.dependencies_count,
                "findings_generated_count": r.findings_count,
                "error_summary": r.error_message,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ],
    }


@router.post("/connect")
def connect_repository(
    req: ConnectRepoRequest,
    current_user: User = Depends(require_roles(MUTATING_REPO_ROLES)),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == req.project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    is_safe, reason = RepositoryIngestionService.validate_repo_url(req.repo_url)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Invalid repository URL: {reason}")

    parsed = urlparse(req.repo_url.strip())
    inferred_name = parsed.path.strip("/").removesuffix(".git") or project.name

    generated_webhook_secret: Optional[str] = None
    conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == req.project_id).first()
    if not conn:
        raw_webhook_secret = (req.webhook_secret or "").strip() or secrets.token_hex(24)
        generated_webhook_secret = raw_webhook_secret
        meta_init = {"installation_id": req.installation_id} if req.installation_id else {}
        conn = RepositoryConnection(
            org_id=current_user.org_id,
            project_id=req.project_id,
            provider=req.provider.lower(),
            repo_name=inferred_name,
            repo_url=req.repo_url.strip(),
            branch=req.branch,
            default_branch=req.branch,
            encrypted_access_token=encrypt_credential(req.access_token) if req.access_token else "",
            webhook_secret=encrypt_credential(raw_webhook_secret),
            metadata_json=meta_init,
            status="connected",
            last_sync_status="ready",
        )
        db.add(conn)
    else:
        conn.org_id = current_user.org_id
        conn.provider = req.provider.lower()
        conn.repo_name = inferred_name
        conn.repo_url = req.repo_url.strip()
        conn.branch = req.branch
        conn.selected_branch = req.branch
        if req.installation_id is not None:
            meta_upd = dict(conn.metadata_json or {})
            meta_upd["installation_id"] = req.installation_id
            conn.metadata_json = meta_upd
        if req.access_token:
            conn.encrypted_access_token = encrypt_credential(req.access_token)
        if req.webhook_secret:
            conn.webhook_secret = encrypt_credential(req.webhook_secret)
            generated_webhook_secret = req.webhook_secret
        elif not conn.webhook_secret:
            generated_webhook_secret = secrets.token_hex(24)
            conn.webhook_secret = encrypt_credential(generated_webhook_secret)
        conn.status = "connected"

    project.repository_url = req.repo_url.strip()
    db.commit()
    db.refresh(conn)

    resp: Dict[str, Any] = {
        "message": f"Successfully connected repository to project {project.name}",
        "repository_id": conn.id,
        "status": conn.status,
        "provider": conn.provider,
        "repo_url": conn.repo_url,
        "branch": conn.selected_branch or conn.branch,
        "credentials_stored": bool(conn.encrypted_access_token or (conn.metadata_json or {}).get("installation_id")),
        "webhook_configured": bool(conn.webhook_secret),
    }
    if generated_webhook_secret:
        resp["webhook_secret"] = generated_webhook_secret
    return resp


@router.post("/upload-zip")
async def upload_repository_zip(
    project_id: str = Form(...),
    branch: str = Form("main"),
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles(MUTATING_REPO_ROLES)),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP archives are supported")

    content = await file.read()
    if len(content) > RepositoryIngestionService.MAX_REPO_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="ZIP archive exceeds 100MB maximum upload limit")

    conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
    if not conn:
        conn = RepositoryConnection(
            org_id=current_user.org_id,
            project_id=project_id,
            provider="local_upload",
            repo_name=file.filename,
            repo_url=file.filename,
            branch=branch,
            status="syncing",
            last_sync_status=SYNC_STATE_QUEUED,
        )
        db.add(conn)
        db.flush()
    else:
        if conn.local_path and os.path.exists(conn.local_path):
            shutil.rmtree(conn.local_path, ignore_errors=True)
        conn.local_path = None
        conn.org_id = current_user.org_id
        conn.provider = "local_upload"
        conn.repo_name = file.filename
        conn.repo_url = file.filename
        conn.branch = branch
        conn.selected_branch = branch
        conn.status = "syncing"
        conn.last_sync_status = SYNC_STATE_QUEUED
        db.flush()

    excluded_paths = (conn.metadata_json or {}).get("excluded_paths")
    ingestion_run = RepositoryIngestionRun(
        org_id=current_user.org_id,
        project_id=project_id,
        repo_connection_id=conn.id,
        provider="local_upload",
        branch=branch,
        status=SYNC_STATE_ANALYSING,
        progress_pct=50,
        analyzer_version=RepositoryIngestionService.ANALYZER_VERSION,
        started_at=datetime.utcnow(),
    )
    db.add(ingestion_run)
    db.commit()
    db.refresh(ingestion_run)

    svc = RepositoryIngestionService()
    try:
        result = await svc.ingest_repository(
            zip_bytes=content,
            branch=branch,
            provider="local_upload",
            excluded_paths=excluded_paths,
        )
        ingestion_run.status = SYNC_STATE_PERSISTING
        db.commit()

        snapshot, reused = persist_ingestion_snapshot(
            db=db,
            org_id=current_user.org_id,
            project_id=project_id,
            ingestion_result=result,
            repo_conn=conn,
            ingestion_run=ingestion_run,
            repo_url_or_filename=file.filename,
        )
    except (ArchiveSecurityError, UnsafeRepositoryURLError, ValueError) as e:
        ingestion_run.status = SYNC_STATE_FAILED
        ingestion_run.error_message = str(e)[:1000]
        ingestion_run.completed_at = datetime.utcnow()
        conn.status = "failed"
        conn.last_sync_status = SYNC_STATE_FAILED
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        ingestion_run.status = SYNC_STATE_FAILED
        ingestion_run.error_message = str(e)[:1000]
        ingestion_run.completed_at = datetime.utcnow()
        conn.status = "failed"
        conn.last_sync_status = SYNC_STATE_FAILED
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to process archive: {str(e)}")

    code_analysis = result.get("code_analysis") or {}
    profile = result.get("profile") or {}
    deps = result.get("dependencies") or []
    manifests_found = len({d.get("file_source") for d in deps if d.get("file_source")})

    return {
        "message": (
            f"Successfully ingested repository ZIP ({snapshot.files_analyzed} analyzed files, "
            f"{snapshot.lines_of_code} LOC, {len(deps)} dependencies)"
        ),
        "project_id": project_id,
        "snapshot_id": snapshot.id,
        "ingestion_run_id": ingestion_run.id,
        "idempotent_reused": reused,
        "commit_sha": snapshot.commit_sha,
        "file_count": snapshot.files_analyzed,
        "files_examined": snapshot.files_examined,
        "lines_of_code": snapshot.lines_of_code,
        "languages": profile.get("languages", []),
        "frameworks": profile.get("frameworks", []),
        "manifests_found": manifests_found,
        "dependencies_discovered": len(deps),
        "findings_discovered": len(code_analysis.get("findings", [])),
        "sync_state": SYNC_STATE_COMPLETED,
        "status": conn.status,
    }


class AsyncSyncRequest(BaseModel):
    branch: Optional[str] = None
    auth_token: Optional[str] = None


@router.post("/{project_id}/sync-async")
async def trigger_async_sync(
    project_id: str,
    background_tasks: BackgroundTasks,
    payload: Optional[AsyncSyncRequest] = None,
    current_user: User = Depends(require_roles(MUTATING_REPO_ROLES)),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
    if not conn or not conn.repo_url or conn.provider == "local_upload":
        raise HTTPException(
            status_code=400,
            detail="No remote repository configured for this project. Connect a GitHub, GitLab, or Bitbucket repository first.",
        )

    branch = (payload and payload.branch) or conn.selected_branch or conn.branch or "main"
    auth_token = payload and payload.auth_token
    if auth_token:
        conn.encrypted_access_token = encrypt_credential(auth_token)

    try:
        job_id = ingestion_job_manager.create_job(
            project_id=project_id,
            org_id=current_user.org_id,
            provider=conn.provider,
            branch=branch,
            repository_connection_id=conn.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))

    conn.status = "syncing"
    conn.last_sync_status = SYNC_STATE_QUEUED
    db.commit()

    background_tasks.add_task(
        repo_ingestion_module.execute_async_ingestion,
        job_id=job_id,
        project_id=project_id,
        org_id=current_user.org_id,
        repo_url=conn.repo_url,
        auth_token=auth_token,
        branch=branch,
        provider=conn.provider,
    )

    return {
        "message": "Repository synchronization initiated in background",
        "job_id": job_id,
        "status": "pending",
        "sync_state": SYNC_STATE_QUEUED,
        "progress": 0,
    }


@router.get("/jobs/{job_id}")
def get_ingestion_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Poll asynchronous repository ingestion progress and explicit sync state."""
    job = ingestion_job_manager.get_job(job_id, org_id=current_user.org_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_ingestion_job(
    job_id: str,
    current_user: User = Depends(require_roles(MUTATING_REPO_ROLES)),
):
    """Cancel a queued or running repository ingestion job."""
    job = ingestion_job_manager.get_job(job_id, org_id=current_user.org_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    if job.get("sync_state") in (SYNC_STATE_COMPLETED, SYNC_STATE_FAILED, SYNC_STATE_CANCELLED):
        return {"message": f"Job is already in terminal state {job.get('sync_state')}", "job": job}
    ingestion_job_manager.update_job(
        job_id,
        status=SYNC_STATE_CANCELLED,
        progress=job.get("progress", 0),
        stage="Cancelled by user",
    )
    return {
        "message": "Ingestion job cancelled",
        "job_id": job_id,
        "sync_state": SYNC_STATE_CANCELLED,
    }


@router.delete("/{project_id}")
@router.delete("/{project_id}/connection")
def disconnect_repository(
    project_id: str,
    current_user: User = Depends(require_roles(ADMIN_REPO_ROLES)),
    db: Session = Depends(get_db),
):
    """Safely disconnect a repository from a project and clean any local workspace."""
    project = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="No repository connected to this project")

    if conn.local_path and os.path.exists(conn.local_path):
        shutil.rmtree(conn.local_path, ignore_errors=True)

    db.delete(conn)
    project.repository_url = None
    db.commit()

    return {"message": "Repository connection removed and disconnected successfully"}


def _match_repository_connection(db: Session, repo_url: str) -> Optional[RepositoryConnection]:
    clean = repo_url.strip().rstrip("/")
    base = clean[:-4] if clean.endswith(".git") else clean
    return (
        db.query(RepositoryConnection)
        .filter(
            (RepositoryConnection.repo_url == repo_url)
            | (RepositoryConnection.repo_url == clean)
            | (RepositoryConnection.repo_url == base)
            | (RepositoryConnection.repo_url == f"{base}.git")
        )
        .first()
    )


def _record_webhook_delivery_idempotent(
    db: Session,
    provider: str,
    delivery_id: str,
    event_type: str,
    conn: RepositoryConnection,
    raw_body: bytes,
    branch: str = "main",
    commit_sha: str = "",
) -> bool:
    """Returns True if new delivery recorded, False if duplicate replay."""
    scoped_delivery_id = f"{provider}:{delivery_id}"
    existing = (
        db.query(WebhookDeliveryEvent)
        .filter(
            WebhookDeliveryEvent.provider == provider,
            WebhookDeliveryEvent.delivery_id == scoped_delivery_id,
        )
        .first()
    )
    if existing is not None:
        return False

    rec = WebhookDeliveryEvent(
        provider=provider,
        delivery_id=scoped_delivery_id,
        org_id=conn.org_id,
        project_id=conn.project_id,
        repo_connection_id=conn.id,
        event_type=event_type,
        branch=branch,
        commit_sha=commit_sha,
        status="queued",
    )
    db.add(rec)
    db.flush()
    return True


@router.post("/webhook/{provider}")
async def handle_repo_webhook(
    provider: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Enterprise CI/CD repository push and pull-request webhook listener.
    Supports GitHub, GitLab, and Bitbucket with cryptographic signature/token
    verification, delivery replay deduplication, branch matching, and async ingestion.
    """
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed JSON webhook body")

    provider_clean = provider.lower()

    # 1. GitHub webhook handling (push & pull_request)
    if provider_clean == "github":
        event = request.headers.get("X-GitHub-Event", "push")
        if event == "ping":
            return {"status": "pong", "message": "GitHub webhook ping verified"}

        repo_info = payload.get("repository") or {}
        repo_url = repo_info.get("html_url") or repo_info.get("clone_url")
        if not repo_url:
            return {"status": "ignored", "reason": "No repository URL in payload"}

        conn = _match_repository_connection(db, repo_url)
        if not conn:
            return {"status": "ignored", "reason": "Repository not registered"}

        secret = _resolve_webhook_secret(conn)
        if not secret:
            raise HTTPException(status_code=401, detail="Webhook secret is not configured for this repository")
        sig = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise HTTPException(status_code=401, detail="Invalid GitHub webhook HMAC-SHA256 signature")

        target_branch = conn.selected_branch or conn.branch or "main"
        if event == "pull_request":
            action = payload.get("action", "")
            if action not in ("opened", "synchronize", "reopened"):
                return {"status": "ignored", "reason": f"Pull request action '{action}' ignored"}
            pr = payload.get("pull_request") or {}
            base_branch = (pr.get("base") or {}).get("ref", "")
            head_info = pr.get("head") or {}
            if base_branch != target_branch:
                return {
                    "status": "ignored",
                    "reason": f"PR targets '{base_branch}', monitored branch is '{target_branch}'",
                }
            branch = head_info.get("ref") or target_branch
            commit_sha = (head_info.get("sha") or "")[:64]
            commit_msg = f"PR #{payload.get('number')}: {pr.get('title', 'Pull request sync')}"
            commit_author = ((pr.get("user") or {}).get("login") or "GitHub PR")
        else:
            ref = payload.get("ref", "")
            branch = ref.split("/")[-1] if "/" in ref else ref
            if branch != target_branch:
                return {
                    "status": "ignored",
                    "reason": f"Push was on branch '{branch}', monitored branch is '{target_branch}'",
                }
            head_commit = payload.get("head_commit") or {}
            commit_sha = (head_commit.get("id") or payload.get("after") or "")[:64]
            commit_msg = head_commit.get("message", "Incremental push synchronization")
            commit_author = (head_commit.get("author") or {}).get("name", "GitHub Webhook")

        delivery_id = (
            request.headers.get("X-GitHub-Delivery")
            or hashlib.sha256(raw_body).hexdigest()
        )
        if not _record_webhook_delivery_idempotent(db, "github", delivery_id, event, conn, raw_body):
            return {"status": "duplicate_ignored", "delivery_id": delivery_id}

        project = db.query(Project).filter(Project.id == conn.project_id).first()
        effective_org_id = conn.org_id or (project.org_id if project else "")

        conn.commit_sha = commit_sha
        conn.commit_message = commit_msg
        conn.commit_author = commit_author
        conn.status = "sync_queued"
        conn.last_sync_status = SYNC_STATE_QUEUED
        conn.last_synced_at = datetime.utcnow()
        db.commit()

        job_id = None
        try:
            job_id = ingestion_job_manager.create_job(
                project_id=conn.project_id,
                org_id=effective_org_id,
                provider="github",
                branch=branch,
                repository_connection_id=conn.id,
            )
            background_tasks.add_task(
                execute_async_ingestion,
                job_id=job_id,
                project_id=conn.project_id,
                org_id=effective_org_id,
                repo_url=conn.repo_url,
                branch=branch,
                provider="github",
            )
        except Exception as e:
            logger.warning(f"Could not enqueue async job for GitHub webhook: {e}")

        return {
            "status": "accepted",
            "event": event,
            "project_id": conn.project_id,
            "branch": branch,
            "commit_sha": conn.commit_sha,
            "job_id": job_id,
        }

    # 2. GitLab webhook handling (Push Hook & Merge Request Hook)
    elif provider_clean == "gitlab":
        event = request.headers.get("X-Gitlab-Event", "Push Hook")
        proj_info = payload.get("project") or {}
        repo_url = proj_info.get("web_url") or proj_info.get("git_http_url")
        if not repo_url:
            return {"status": "ignored", "reason": "No project URL in GitLab payload"}

        conn = _match_repository_connection(db, repo_url)
        if not conn:
            return {"status": "ignored", "reason": "Repository not registered"}

        secret = _resolve_webhook_secret(conn)
        if not secret:
            raise HTTPException(status_code=401, detail="Webhook secret is not configured for this repository")
        token_hdr = request.headers.get("X-Gitlab-Token", "")
        if not hmac.compare_digest(secret, token_hdr):
            raise HTTPException(status_code=401, detail="Invalid GitLab webhook secret token")

        target_branch = conn.selected_branch or conn.branch or "main"
        if event == "Merge Request Hook" or payload.get("object_kind") == "merge_request":
            attrs = payload.get("object_attributes") or {}
            action = attrs.get("action", "open")
            if action not in ("open", "update", "reopen"):
                return {"status": "ignored", "reason": f"Merge request action '{action}' ignored"}
            mr_target = attrs.get("target_branch", "")
            if mr_target != target_branch:
                return {
                    "status": "ignored",
                    "reason": f"MR targets '{mr_target}', monitored branch is '{target_branch}'",
                }
            branch = attrs.get("source_branch") or target_branch
            last_commit = attrs.get("last_commit") or {}
            commit_sha = (last_commit.get("id") or "")[:64]
            commit_msg = f"MR !{attrs.get('iid')}: {attrs.get('title', 'Merge request sync')}"
            commit_author = (payload.get("user") or {}).get("name", "GitLab MR")
        else:
            ref = payload.get("ref", "")
            branch = ref.split("/")[-1] if "/" in ref else ref
            if branch != target_branch:
                return {
                    "status": "ignored",
                    "reason": f"Push on '{branch}', monitored branch is '{target_branch}'",
                }
            commits = payload.get("commits") or []
            last_commit = commits[-1] if commits else {}
            commit_sha = (payload.get("checkout_sha") or last_commit.get("id") or "")[:64]
            commit_msg = last_commit.get("message", "GitLab webhook sync")
            commit_author = payload.get("user_name", "GitLab Webhook")

        delivery_id = (
            request.headers.get("X-Gitlab-Event-UUID")
            or hashlib.sha256(raw_body).hexdigest()
        )
        if not _record_webhook_delivery_idempotent(db, "gitlab", delivery_id, event, conn, raw_body):
            return {"status": "duplicate_ignored", "delivery_id": delivery_id}

        project = db.query(Project).filter(Project.id == conn.project_id).first()
        effective_org_id = conn.org_id or (project.org_id if project else "")

        conn.commit_sha = commit_sha
        conn.commit_message = commit_msg
        conn.commit_author = commit_author
        conn.status = "sync_queued"
        conn.last_sync_status = SYNC_STATE_QUEUED
        conn.last_synced_at = datetime.utcnow()
        db.commit()

        job_id = None
        try:
            job_id = ingestion_job_manager.create_job(
                project_id=conn.project_id,
                org_id=effective_org_id,
                provider="gitlab",
                branch=branch,
                repository_connection_id=conn.id,
            )
            background_tasks.add_task(
                execute_async_ingestion,
                job_id=job_id,
                project_id=conn.project_id,
                org_id=effective_org_id,
                repo_url=conn.repo_url,
                branch=branch,
                provider="gitlab",
            )
        except Exception as e:
            logger.warning(f"Could not enqueue async job for GitLab webhook: {e}")

        return {
            "status": "accepted",
            "event": event,
            "project_id": conn.project_id,
            "branch": branch,
            "commit_sha": conn.commit_sha,
            "job_id": job_id,
        }

    # 3. Bitbucket webhook handling (repo:push & pullrequest:created/updated)
    elif provider_clean == "bitbucket":
        event = request.headers.get("X-Event-Key", "repo:push")
        repo_info = payload.get("repository") or {}
        repo_url = ((repo_info.get("links") or {}).get("html") or {}).get("href")
        if not repo_url:
            return {"status": "ignored", "reason": "No repository URL in Bitbucket payload"}

        conn = _match_repository_connection(db, repo_url)
        if not conn:
            return {"status": "ignored", "reason": "Repository not registered"}

        secret = _resolve_webhook_secret(conn)
        if not secret:
            raise HTTPException(status_code=401, detail="Webhook secret is not configured for this repository")
        sig = request.headers.get("X-Hub-Signature", "")
        expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise HTTPException(status_code=401, detail="Invalid Bitbucket webhook HMAC-SHA256 signature")

        target_branch = conn.selected_branch or conn.branch or "main"
        branch = target_branch
        commit_sha = ""
        commit_msg = "Bitbucket webhook sync"
        commit_author = "Bitbucket Webhook"

        if event.startswith("pullrequest:"):
            if event not in ("pullrequest:created", "pullrequest:updated"):
                return {"status": "ignored", "reason": f"Bitbucket PR event '{event}' ignored"}
            pr = payload.get("pullrequest") or {}
            dest_branch = ((pr.get("destination") or {}).get("branch") or {}).get("name", "")
            if dest_branch != target_branch:
                return {
                    "status": "ignored",
                    "reason": f"PR targets '{dest_branch}', monitored branch is '{target_branch}'",
                }
            src = pr.get("source") or {}
            branch = (src.get("branch") or {}).get("name") or target_branch
            commit_sha = ((src.get("commit") or {}).get("hash") or "")[:64]
            commit_msg = f"PR #{pr.get('id')}: {pr.get('title', 'Bitbucket PR sync')}"
            commit_author = ((pr.get("author") or {}).get("display_name") or "Bitbucket PR")
        else:
            changes = (payload.get("push") or {}).get("changes") or []
            if changes:
                new_change = changes[0].get("new") or {}
                branch = new_change.get("name", target_branch)
                if branch != target_branch:
                    return {
                        "status": "ignored",
                        "reason": f"Push on '{branch}', monitored branch is '{target_branch}'",
                    }
                target_commit = new_change.get("target") or {}
                commit_sha = (target_commit.get("hash") or "")[:64]
                commit_msg = target_commit.get("message", "Bitbucket webhook sync")
                commit_author = (target_commit.get("author") or {}).get("raw", "Bitbucket Webhook")

        delivery_id = (
            request.headers.get("X-Request-UUID")
            or hashlib.sha256(raw_body).hexdigest()
        )
        if not _record_webhook_delivery_idempotent(db, "bitbucket", delivery_id, event, conn, raw_body):
            return {"status": "duplicate_ignored", "delivery_id": delivery_id}

        project = db.query(Project).filter(Project.id == conn.project_id).first()
        effective_org_id = conn.org_id or (project.org_id if project else "")

        conn.commit_sha = commit_sha
        conn.commit_message = commit_msg
        conn.commit_author = commit_author
        conn.status = "sync_queued"
        conn.last_sync_status = SYNC_STATE_QUEUED
        conn.last_synced_at = datetime.utcnow()
        db.commit()

        job_id = None
        try:
            job_id = ingestion_job_manager.create_job(
                project_id=conn.project_id,
                org_id=effective_org_id,
                provider="bitbucket",
                branch=branch,
                repository_connection_id=conn.id,
            )
            background_tasks.add_task(
                execute_async_ingestion,
                job_id=job_id,
                project_id=conn.project_id,
                org_id=effective_org_id,
                repo_url=conn.repo_url,
                branch=branch,
                provider="bitbucket",
            )
        except Exception as e:
            logger.warning(f"Could not enqueue async job for Bitbucket webhook: {e}")

        return {
            "status": "accepted",
            "event": event,
            "project_id": conn.project_id,
            "branch": branch,
            "commit_sha": conn.commit_sha,
            "job_id": job_id,
        }

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported webhook provider '{provider}'")


# --- Commercial Repository UX Configuration Endpoints ---


class RepoSettingsRequest(BaseModel):
    selected_branch: Optional[str] = None
    review_frequency: Optional[str] = "weekly"
    excluded_paths: Optional[List[str]] = None
    auto_assess_on_push: Optional[bool] = True


@router.get("/{project_id}/settings")
def get_repo_settings(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve repository configuration settings and branches for a project."""
    proj = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="No repository connected to this project")

    meta = conn.metadata_json or {}
    return {
        "project_id": project_id,
        "repo_name": conn.repo_name,
        "provider": conn.provider,
        "selected_branch": conn.selected_branch or conn.branch or "main",
        "default_branch": conn.default_branch or "main",
        "review_frequency": meta.get("review_frequency", "weekly"),
        "excluded_paths": meta.get("excluded_paths", ["node_modules/**", "dist/**", "vendor/**"]),
        "auto_assess_on_push": meta.get("auto_assess_on_push", True),
        "status": conn.status,
        "sync_state": conn.last_sync_status,
        "last_synced_at": conn.last_synced_at,
    }


@router.put("/{project_id}/settings")
def update_repo_settings(
    project_id: str,
    req: RepoSettingsRequest,
    current_user: User = Depends(require_roles(MUTATING_REPO_ROLES)),
    db: Session = Depends(get_db),
):
    """Update repository branch, review frequency, and exclusion paths."""
    proj = db.query(Project).filter(Project.id == project_id, Project.org_id == current_user.org_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="No repository connected to this project")

    if req.selected_branch:
        conn.selected_branch = req.selected_branch
        conn.branch = req.selected_branch

    meta = dict(conn.metadata_json or {})
    if req.review_frequency is not None:
        meta["review_frequency"] = req.review_frequency
    if req.excluded_paths is not None:
        meta["excluded_paths"] = req.excluded_paths
    if req.auto_assess_on_push is not None:
        meta["auto_assess_on_push"] = req.auto_assess_on_push

    conn.metadata_json = meta
    db.commit()
    return {
        "message": "Repository settings updated successfully",
        "settings": meta,
        "selected_branch": conn.selected_branch,
    }
