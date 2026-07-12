"""SMART Backend Services — the EMR-standard system login for the clinic backend
(ADR-0009).

OAuth2 `client_credentials` where the client authenticates with a signed JWT assertion
(RS384): iss = sub = client_id, aud = the token endpoint, short exp, unique jti.
Scopes are `system/...` (least privilege). The signing private key comes from the
secret manager — never the repo or DB.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
DEFAULT_SYSTEM_SCOPES = ("system/Observation.read",)

# SMART Backend Services requires a short-lived assertion (max 5 minutes).
_MAX_LIFETIME = timedelta(minutes=5)


def build_client_assertion(
    *,
    client_id: str,
    token_endpoint: str,
    private_key_pem: str,
    kid: str | None = None,
    lifetime: timedelta = _MAX_LIFETIME,
    now: datetime | None = None,
) -> str:
    """Sign the RS384 JWT client assertion that authenticates the clinic backend."""
    issued_at = now or datetime.now(UTC)
    lifetime = min(lifetime, _MAX_LIFETIME)
    claims = {
        "iss": client_id,
        "sub": client_id,
        "aud": token_endpoint,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + lifetime).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    headers = {"kid": kid} if kid else None
    return jwt.encode(claims, private_key_pem, algorithm="RS384", headers=headers)


def build_backend_token_request(
    *,
    assertion: str,
    scopes: tuple[str, ...] = DEFAULT_SYSTEM_SCOPES,
) -> dict[str, str]:
    """Form parameters for the Backend Services token request."""
    return {
        "grant_type": "client_credentials",
        "scope": " ".join(scopes),
        "client_assertion_type": CLIENT_ASSERTION_TYPE,
        "client_assertion": assertion,
    }
