"""Tests for SMART Backend Services auth (ADR-0009) — the clinic backend's standard
EMR login: RS384 JWT client assertion + client_credentials request shape.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.emr.backend_auth import (
    CLIENT_ASSERTION_TYPE,
    build_backend_token_request,
    build_client_assertion,
)

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_PEM = _KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
_PUBLIC_PEM = (
    _KEY.public_key()
    .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    .decode()
)


def _decode(assertion: str) -> dict[str, object]:
    return jwt.decode(
        assertion,
        _PUBLIC_PEM,
        algorithms=["RS384"],  # RS384 is what SMART Backend Services requires
        audience="https://ehr.example/oauth/token",
    )


def test_assertion_carries_required_smart_claims() -> None:
    assertion = build_client_assertion(
        client_id="clinic-backend",
        token_endpoint="https://ehr.example/oauth/token",
        private_key_pem=_PRIVATE_PEM,
        kid="key-1",
    )
    claims = _decode(assertion)
    assert claims["iss"] == "clinic-backend"
    assert claims["sub"] == "clinic-backend"
    assert claims["aud"] == "https://ehr.example/oauth/token"
    assert isinstance(claims["jti"], str) and claims["jti"]
    assert jwt.get_unverified_header(assertion)["kid"] == "key-1"


def test_jti_is_unique_per_assertion() -> None:
    common = {
        "client_id": "clinic-backend",
        "token_endpoint": "https://ehr.example/oauth/token",
        "private_key_pem": _PRIVATE_PEM,
    }
    a, b = build_client_assertion(**common), build_client_assertion(**common)
    assert _decode(a)["jti"] != _decode(b)["jti"]


def test_lifetime_is_clamped_to_five_minutes() -> None:
    now = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)
    assertion = build_client_assertion(
        client_id="clinic-backend",
        token_endpoint="https://ehr.example/oauth/token",
        private_key_pem=_PRIVATE_PEM,
        lifetime=timedelta(hours=2),  # over the SMART max — must be clamped
        now=now,
    )
    claims = jwt.decode(
        assertion,
        _PUBLIC_PEM,
        algorithms=["RS384"],
        audience="https://ehr.example/oauth/token",
        options={"verify_exp": False},
    )
    assert claims["exp"] == int((now + timedelta(minutes=5)).timestamp())


def test_backend_token_request_shape() -> None:
    body = build_backend_token_request(assertion="signed.jwt.here")
    assert body["grant_type"] == "client_credentials"
    assert body["client_assertion_type"] == CLIENT_ASSERTION_TYPE
    assert body["client_assertion"] == "signed.jwt.here"
    assert body["scope"] == "system/Observation.read"  # least privilege by default
