"""SMART on FHIR / OAuth2 helpers — pure and unit-tested (ADR-0008).

Builds the PKCE pair, the authorization URL, and the token-exchange request. No I/O here
so the security-critical bits (PKCE, scopes, params) are locked by tests.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import urlencode

# Default scopes for a patient reading their own labs (least privilege).
DEFAULT_SCOPES = (
    "launch/patient",
    "patient/Observation.read",
    "openid",
    "fhirUser",
    "offline_access",
)


def generate_code_verifier(n_bytes: int = 64) -> str:
    """A high-entropy PKCE code_verifier (RFC 7636), URL-safe, unpadded."""
    return base64.urlsafe_b64encode(secrets.token_bytes(n_bytes)).rstrip(b"=").decode()


def code_challenge_for(verifier: str) -> str:
    """S256 PKCE challenge = base64url(sha256(verifier)), unpadded (RFC 7636)."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def build_authorize_url(
    *,
    authorization_endpoint: str,
    client_id: str,
    redirect_uri: str,
    fhir_base: str,
    state: str,
    code_challenge: str,
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
) -> str:
    """Construct the SMART authorization-code (PKCE) URL for standalone patient launch."""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "aud": fhir_base,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{authorization_endpoint}?{urlencode(params)}"


def build_token_request(
    *,
    client_id: str,
    redirect_uri: str,
    code: str,
    code_verifier: str,
) -> dict[str, str]:
    """Form parameters for the authorization-code token exchange (with PKCE)."""
    return {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
