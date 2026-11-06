import os
import logging
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode
import httpx

from app.services.crypto_service import encrypt_credential, decrypt_credential

logger = logging.getLogger(__name__)

class BitbucketIntegrationError(Exception):
    """Raised when Bitbucket API operations or authorization fail."""
    pass

class BitbucketService:
    """
    Commercial-grade Bitbucket repository integration service.
    Implements OAuth 2.0 authorization, repository discovery, branch selection,
    and secure credential management for Atlassian Bitbucket Cloud.
    """

    AUTH_URL = "https://bitbucket.org/site/oauth2/authorize"
    TOKEN_URL = "https://bitbucket.org/site/oauth2/access_token"
    API_BASE = "https://api.bitbucket.org/2.0"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ):
        self.client_id = client_id or os.getenv("BITBUCKET_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("BITBUCKET_CLIENT_SECRET")

    @property
    def is_configured(self) -> bool:
        """Return True if Bitbucket OAuth credentials are set."""
        return bool(self.client_id and self.client_secret)

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Generate Bitbucket OAuth authorization URL requesting repository read scopes."""
        if not self.is_configured:
            raise BitbucketIntegrationError("Bitbucket integration is not configured. Missing BITBUCKET_CLIENT_ID or BITBUCKET_CLIENT_SECRET.")

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "state": state
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange authorization code for an OAuth access token using HTTP Basic auth."""
        if not self.is_configured:
            raise BitbucketIntegrationError("Bitbucket integration is not configured.")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(
                    self.TOKEN_URL,
                    data=data,
                    auth=(self.client_id, self.client_secret),
                    headers={"Accept": "application/json"}
                )
                if res.status_code != 200:
                    logger.error("Bitbucket OAuth token exchange failed (%s): %s", res.status_code, res.text)
                    raise BitbucketIntegrationError(f"Bitbucket token exchange failed: HTTP {res.status_code}")
                return res.json()
        except httpx.RequestError as e:
            logger.error("Network error during Bitbucket token exchange: %s", e)
            raise BitbucketIntegrationError(f"Network error contacting Bitbucket: {str(e)}")

    def list_repositories(self, access_token: str) -> List[Dict[str, Any]]:
        """List repositories accessible to the authenticated Bitbucket user."""
        if not access_token or not access_token.strip():
            raise BitbucketIntegrationError("Valid Bitbucket access token required")

        url = f"{self.API_BASE}/repositories?role=member&pagelen=100"
        headers = {
            "Authorization": f"Bearer {access_token.strip()}",
            "Accept": "application/json"
        }

        try:
            with httpx.Client(timeout=20.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code == 401:
                    raise BitbucketIntegrationError("Bitbucket authorization expired or revoked. Please reconnect your account.")
                if res.status_code != 200:
                    raise BitbucketIntegrationError(f"Failed to list Bitbucket repositories: HTTP {res.status_code}")

                data = res.json()
                values = data.get("values", [])
                return [
                    {
                        "uuid": r.get("uuid"),
                        "full_name": r.get("full_name"),
                        "name": r.get("name"),
                        "is_private": r.get("is_private", True),
                        "mainbranch": r.get("mainbranch", {}).get("name", "master"),
                        "web_url": r.get("links", {}).get("html", {}).get("href", ""),
                        "clone_url": next(
                            (c.get("href") for c in r.get("links", {}).get("clone", []) if c.get("name") == "https"),
                            ""
                        ),
                        "description": r.get("description", "")
                    }
                    for r in values
                ]
        except httpx.RequestError as e:
            raise BitbucketIntegrationError(f"Network error contacting Bitbucket: {str(e)}")

    def list_repository_branches(self, workspace: str, repo_slug: str, access_token: str) -> List[str]:
        """List branches for a Bitbucket repository."""
        if not access_token:
            raise BitbucketIntegrationError("Bitbucket access token required")

        url = f"{self.API_BASE}/repositories/{workspace}/{repo_slug}/refs/branches?pagelen=100"
        headers = {
            "Authorization": f"Bearer {access_token.strip()}",
            "Accept": "application/json"
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code != 200:
                    raise BitbucketIntegrationError(f"Failed to list Bitbucket branches: HTTP {res.status_code}")
                data = res.json()
                return [b["name"] for b in data.get("values", [])]
        except httpx.RequestError as e:
            raise BitbucketIntegrationError(f"Network error contacting Bitbucket: {str(e)}")
