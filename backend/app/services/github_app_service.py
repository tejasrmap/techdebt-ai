import os
import time
import logging
from typing import Optional, Dict, Any, List
import httpx
from jose import jwt

from app.config import settings
from app.services.crypto_service import encrypt_credential, decrypt_credential

logger = logging.getLogger(__name__)

class GitHubAppError(Exception):
    """Raised when GitHub App operations fail."""
    pass

class GitHubAppService:
    """
    Commercial-grade GitHub App integration service.
    Implements GitHub App installation flow, RS256 JWT app authentication,
    short-lived installation tokens, repository discovery, and branch selection.
    """

    GITHUB_API_BASE = "https://api.github.com"

    def __init__(
        self,
        app_id: Optional[str] = None,
        private_key: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ):
        self.app_id = app_id or os.getenv("GITHUB_APP_ID")
        self.private_key = private_key or os.getenv("GITHUB_APP_PRIVATE_KEY")
        self.client_id = client_id or os.getenv("GITHUB_APP_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("GITHUB_APP_CLIENT_SECRET")
        # In-memory token cache: installation_id -> {"token": str, "expires_at": float}
        self._token_cache: Dict[str, Dict[str, Any]] = {}

    @property
    def is_configured(self) -> bool:
        """Return True if minimum required credentials for GitHub App are present."""
        return bool(self.app_id and self.private_key)

    def generate_app_jwt(self) -> str:
        """
        Generate RS256 JWT for authenticating as the GitHub App.
        Valid for 10 minutes as per GitHub documentation.
        """
        if not self.is_configured:
            raise GitHubAppError("GitHub App is not configured. Missing GITHUB_APP_ID or GITHUB_APP_PRIVATE_KEY.")

        now = int(time.time())
        payload = {
            "iat": now - 60,       # 1 minute clock drift allowance
            "exp": now + (10 * 60), # 10 minutes maximum
            "iss": self.app_id
        }

        try:
            token = jwt.encode(payload, self.private_key, algorithm="RS256")
            return token
        except Exception as e:
            logger.error("Failed to sign GitHub App JWT: %s", e)
            raise GitHubAppError(f"Failed to generate GitHub App JWT: {str(e)}")

    def get_installation_token(self, installation_id: str) -> str:
        """
        Exchange App JWT for an installation access token.
        Caches token until 5 minutes before expiration.
        """
        now = time.time()
        cached = self._token_cache.get(installation_id)
        if cached and cached["expires_at"] > (now + 300):
            return cached["token"]

        jwt_token = self.generate_app_jwt()
        url = f"{self.GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        # Request minimum required permissions
        body = {
            "permissions": {
                "contents": "read",
                "metadata": "read",
                "pull_requests": "read"
            }
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(url, headers=headers, json=body)
                if res.status_code != 201:
                    logger.error("GitHub App token exchange failed (%s): %s", res.status_code, res.text)
                    raise GitHubAppError(f"GitHub App token exchange failed: HTTP {res.status_code}")
                data = res.json()
                token = data["token"]
                # GitHub tokens typically expire in 1 hour
                self._token_cache[installation_id] = {
                    "token": token,
                    "expires_at": now + 3600
                }
                return token
        except httpx.RequestError as e:
            logger.error("Network error during GitHub App token request: %s", e)
            raise GitHubAppError(f"Network error contacting GitHub API: {str(e)}")

    def list_installation_repositories(self, installation_id: str) -> List[Dict[str, Any]]:
        """List repositories accessible to this GitHub App installation."""
        token = self.get_installation_token(installation_id)
        url = f"{self.GITHUB_API_BASE}/installation/repositories?per_page=100"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }

        try:
            with httpx.Client(timeout=20.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code != 200:
                    raise GitHubAppError(f"Failed to list repositories: HTTP {res.status_code}")
                repos = res.json().get("repositories", [])
                return [
                    {
                        "id": r["id"],
                        "name": r["name"],
                        "full_name": r["full_name"],
                        "private": r["private"],
                        "default_branch": r.get("default_branch", "main"),
                        "html_url": r["html_url"],
                        "clone_url": r["clone_url"],
                        "description": r.get("description", "")
                    }
                    for r in repos
                ]
        except httpx.RequestError as e:
            raise GitHubAppError(f"Failed to list repositories: {str(e)}")

    def list_repository_branches(self, repo_full_name: str, installation_id: Optional[str] = None, token: Optional[str] = None) -> List[str]:
        """List branches for a given repository."""
        if not token and installation_id:
            token = self.get_installation_token(installation_id)

        if not token:
            raise GitHubAppError("Authentication token or installation_id required to list branches")

        url = f"{self.GITHUB_API_BASE}/repos/{repo_full_name}/branches?per_page=100"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json"
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code != 200:
                    raise GitHubAppError(f"Failed to list branches: HTTP {res.status_code}")
                branches = res.json()
                return [b["name"] for b in branches]
        except httpx.RequestError as e:
            raise GitHubAppError(f"Failed to list branches: {str(e)}")

    def revoke_installation(self, installation_id: str) -> bool:
        """Revoke cached token and clear local integration state."""
        self._token_cache.pop(installation_id, None)
        return True
