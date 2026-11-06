import os
import logging
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode, quote_plus
import httpx

from app.services.crypto_service import encrypt_credential, decrypt_credential
from app.services.repository_ingestion_service import RepositoryIngestionService, UnsafeRepositoryURLError

logger = logging.getLogger(__name__)

class GitLabIntegrationError(Exception):
    """Raised when GitLab API operations or authorization fail."""
    pass

class GitLabService:
    """
    Commercial-grade GitLab repository integration service.
    Implements OAuth 2.0 authorization, project discovery, branch selection,
    private repository access, and secure credential handling.
    """

    DEFAULT_GITLAB_URL = "https://gitlab.com"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        gitlab_url: Optional[str] = None
    ):
        self.client_id = client_id or os.getenv("GITLAB_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("GITLAB_CLIENT_SECRET")
        self.gitlab_url = (gitlab_url or os.getenv("GITLAB_URL") or self.DEFAULT_GITLAB_URL).rstrip("/")

    @property
    def is_configured(self) -> bool:
        """Return True if minimum OAuth credentials for GitLab are set."""
        return bool(self.client_id and self.client_secret)

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Generate GitLab OAuth authorization URL requesting read_api and read_repository scopes."""
        if not self.is_configured:
            raise GitLabIntegrationError("GitLab integration is not configured. Missing GITLAB_CLIENT_ID or GITLAB_CLIENT_SECRET.")

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": "read_api read_repository"
        }
        return f"{self.gitlab_url}/oauth/authorize?{urlencode(params)}"

    def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange authorization code for an OAuth access token."""
        if not self.is_configured:
            raise GitLabIntegrationError("GitLab integration is not configured.")

        url = f"{self.gitlab_url}/oauth/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(url, json=payload)
                if res.status_code != 200:
                    logger.error("GitLab OAuth token exchange failed (%s): %s", res.status_code, res.text)
                    raise GitLabIntegrationError(f"GitLab token exchange failed: HTTP {res.status_code}")
                return res.json()
        except httpx.RequestError as e:
            logger.error("Network error during GitLab token exchange: %s", e)
            raise GitLabIntegrationError(f"Network error contacting GitLab: {str(e)}")

    def list_user_projects(self, access_token: str) -> List[Dict[str, Any]]:
        """List accessible projects for the authenticated user."""
        if not access_token or not access_token.strip():
            raise GitLabIntegrationError("Valid GitLab access token required")

        url = f"{self.gitlab_url}/api/v4/projects?membership=true&simple=true&per_page=100&order_by=updated_at"
        headers = {
            "Authorization": f"Bearer {access_token.strip()}",
            "Accept": "application/json"
        }

        try:
            with httpx.Client(timeout=20.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code == 401:
                    raise GitLabIntegrationError("GitLab authorization expired or revoked. Please reconnect your account.")
                if res.status_code != 200:
                    raise GitLabIntegrationError(f"Failed to list GitLab projects: HTTP {res.status_code}")

                projects = res.json()
                return [
                    {
                        "id": p["id"],
                        "name": p["name"],
                        "path_with_namespace": p["path_with_namespace"],
                        "visibility": p.get("visibility", "private"),
                        "default_branch": p.get("default_branch", "main"),
                        "web_url": p["web_url"],
                        "http_url_to_repo": p.get("http_url_to_repo", p["web_url"]),
                        "description": p.get("description", "")
                    }
                    for p in projects
                ]
        except httpx.RequestError as e:
            raise GitLabIntegrationError(f"Network error contacting GitLab: {str(e)}")

    def list_project_branches(self, project_id: Any, access_token: str) -> List[str]:
        """List branches for a GitLab project."""
        if not access_token:
            raise GitLabIntegrationError("GitLab access token required")

        # Encode project ID / path for API URL
        proj_encoded = quote_plus(str(project_id))
        url = f"{self.gitlab_url}/api/v4/projects/{proj_encoded}/repository/branches?per_page=100"
        headers = {
            "Authorization": f"Bearer {access_token.strip()}",
            "Accept": "application/json"
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code != 200:
                    raise GitLabIntegrationError(f"Failed to list GitLab branches: HTTP {res.status_code}")
                branches = res.json()
                return [b["name"] for b in branches]
        except httpx.RequestError as e:
            raise GitLabIntegrationError(f"Network error contacting GitLab: {str(e)}")
