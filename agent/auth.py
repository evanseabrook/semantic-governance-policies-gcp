"""Authentication helper for Google Cloud IAM OIDC tokens.

Provides dynamic bearer token generation to authenticate Agent Engine callers
against the Agent Gateway and Cloud Run MCP server.
"""

import logging
import os
from typing import Dict, Optional
from urllib.parse import urlparse

import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import id_token

import urllib.request
import urllib.error

logger = logging.getLogger("agent.auth")


def get_target_audience(target_url: str) -> str:
    """Extract origin service URL suitable as Cloud Run / Gateway OIDC audience.

    Cloud Run requires the audience claim in the OIDC identity token to match the
    service root URL (e.g. https://<service>.a.run.app) without paths like /mcp.
    """
    parsed = urlparse(target_url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return target_url


def get_metadata_server_id_token(audience: str) -> Optional[str]:
    """Fetch OIDC ID token directly from Google Cloud metadata server.

    In Vertex AI Agent Engine and Cloud Run microVMs, the metadata server generates
    authentic OIDC ID tokens for the attached service account or Agent Identity.
    """
    import urllib.parse

    params = urllib.parse.urlencode({"audience": audience, "format": "full"})
    url = f"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?{params}"
    req = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            token = resp.read().decode("utf-8").strip()
            if token and token.startswith("eyJ"):
                logger.info(f"Successfully obtained OIDC ID token from metadata server for audience: {audience}")
                return token
            elif token:
                logger.warning(f"Metadata server returned non-JWT token (len={len(token)}): {token[:15]}...")
    except Exception as e:
        logger.debug(f"Metadata server ID token request not available: {e}")
    return None


def get_oidc_token(target_url: str) -> str:
    """Fetch an OIDC identity token for the given target URL using Application Default Credentials (ADC)
    or Google Cloud Metadata Service (when running inside Agent Engine).

    Args:
        target_url: Target URL or service audience (e.g., https://gateway-url... or Cloud Run URL)

    Returns:
        OIDC JWT token string.
    """
    # Check if a test/override token is provided in the environment
    env_token = os.environ.get("GATEWAY_AUTH_TOKEN")
    if env_token:
        return env_token

    audience = get_target_audience(target_url)

    # For local development against localhost, do not hang waiting for GCE metadata server
    if audience.startswith(("http://localhost", "http://127.0.0.1")):
        return "local-dev-mock-oidc-token"

    # 1. Try direct metadata server (fastest and most reliable inside Agent Engine)
    metadata_token = get_metadata_server_id_token(audience)
    if metadata_token:
        return metadata_token

    # 2. Try google.oauth2.id_token.fetch_id_token
    try:
        auth_req = Request()
        token = id_token.fetch_id_token(auth_req, audience)
        if token:
            return token
    except Exception as e:
        logger.info(
            f"fetch_id_token did not yield token for {audience}: {e}. "
            "Proceeding with Application Default Credentials fallback."
        )

    try:
        credentials, _ = google.auth.default()
        credentials.refresh(Request())
        if hasattr(credentials, "id_token") and credentials.id_token:
            return credentials.id_token
        return credentials.token or "fallback-token"
    except Exception as cred_err:
        logger.warning(f"Default credentials fallback failed: {cred_err}")
        return "unauthenticated-token"


def get_gateway_auth_headers(target_url: str) -> Dict[str, str]:
    """Generate authorization headers for calling the Agent Gateway / MCP server.

    Args:
        target_url: The destination endpoint URL.
    """
    token = get_oidc_token(target_url)
    headers = {
        "Content-Type": "application/json",
        "X-Agent-Identity": "adk-customer-support-agent",
    }
    if token and token.strip() and token not in ("unauthenticated-token", "fallback-token"):
        headers["Authorization"] = f"Bearer {token.strip()}"
    return headers


class DynamicAuthHeaders(dict):
    """Dictionary-like mapping that dynamically produces fresh authentication headers.

    Prevents token expiration when packaged and executed inside Vertex AI Agent Engine.
    """

    def __init__(self, target_url: str):
        super().__init__()
        self.target_url = target_url
        self._get_fresh()

    def _get_fresh(self) -> Dict[str, str]:
        fresh = get_gateway_auth_headers(self.target_url)
        super().clear()
        super().update(fresh)
        return fresh

    def __getitem__(self, key: str) -> str:
        self._get_fresh()
        return super().__getitem__(key)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        self._get_fresh()
        return super().get(key, default)

    def items(self):
        self._get_fresh()
        return super().items()

    def keys(self):
        self._get_fresh()
        return super().keys()

    def values(self):
        self._get_fresh()
        return super().values()

    def copy(self) -> Dict[str, str]:
        return dict(self._get_fresh())

    def __iter__(self):
        self._get_fresh()
        return super().__iter__()

    def __len__(self) -> int:
        self._get_fresh()
        return super().__len__()

    def __contains__(self, key: object) -> bool:
        self._get_fresh()
        return super().__contains__(key)

