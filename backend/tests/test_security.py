"""Tests for password hashing + session tokens (ADR-0010) — the security primitives."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.security import (
    AuthError,
    TokenKind,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)

SECRET = "unit-test-secret"


def test_password_hash_verifies_and_rejects() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"  # never stored in the clear
    assert hashed.startswith("$argon2id$")  # OWASP first-choice algorithm
    assert verify_password(hashed, "correct horse battery staple") is True
    assert verify_password(hashed, "wrong password") is False


def test_token_round_trip() -> None:
    user_id = uuid4()
    token = create_token(user_id=user_id, role="patient", kind=TokenKind.access, secret=SECRET)
    claims = decode_token(token, secret=SECRET, expected_kind=TokenKind.access)
    assert claims.user_id == user_id
    assert claims.role == "patient"
    assert claims.kind is TokenKind.access


def test_expired_token_is_rejected() -> None:
    token = create_token(
        user_id=uuid4(),
        role="patient",
        kind=TokenKind.access,
        secret=SECRET,
        now=datetime.now(UTC) - timedelta(hours=1),
        ttl=timedelta(minutes=5),
    )
    with pytest.raises(AuthError, match="expired"):
        decode_token(token, secret=SECRET, expected_kind=TokenKind.access)


def test_tampered_token_is_rejected() -> None:
    token = create_token(user_id=uuid4(), role="patient", kind=TokenKind.access, secret=SECRET)
    with pytest.raises(AuthError, match="invalid"):
        decode_token(token + "x", secret=SECRET, expected_kind=TokenKind.access)


def test_wrong_secret_is_rejected() -> None:
    token = create_token(user_id=uuid4(), role="patient", kind=TokenKind.access, secret=SECRET)
    with pytest.raises(AuthError):
        decode_token(token, secret="another-secret", expected_kind=TokenKind.access)


def test_token_with_invalid_subject_is_rejected() -> None:
    import jwt as pyjwt

    payload = {
        "sub": "not-a-uuid",
        "role": "patient",
        "kind": "access",
        "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
    }
    token = pyjwt.encode(payload, SECRET, algorithm="HS256")
    with pytest.raises(AuthError, match="subject"):
        decode_token(token, secret=SECRET, expected_kind=TokenKind.access)


def test_refresh_token_cannot_be_used_as_access_token() -> None:
    token = create_token(user_id=uuid4(), role="patient", kind=TokenKind.refresh, secret=SECRET)
    with pytest.raises(AuthError, match="access"):
        decode_token(token, secret=SECRET, expected_kind=TokenKind.access)


def test_access_token_cannot_be_used_as_refresh_token() -> None:
    token = create_token(user_id=uuid4(), role="patient", kind=TokenKind.access, secret=SECRET)
    with pytest.raises(AuthError, match="refresh"):
        decode_token(token, secret=SECRET, expected_kind=TokenKind.refresh)


def test_mfa_pending_token_cannot_be_used_as_access_or_refresh_token() -> None:
    """§1B C6 kind confusion: an mfa_pending token proves only "knows the password" and
    must be useless as a session credential — the same enforcement that stops
    refresh-as-access replay."""
    token = create_token(
        user_id=uuid4(), role="clinician", kind=TokenKind.mfa_pending, secret=SECRET
    )
    with pytest.raises(AuthError, match="access"):
        decode_token(token, secret=SECRET, expected_kind=TokenKind.access)
    with pytest.raises(AuthError, match="refresh"):
        decode_token(token, secret=SECRET, expected_kind=TokenKind.refresh)


def test_access_and_refresh_tokens_cannot_be_used_as_mfa_pending() -> None:
    """The confusion is refused in BOTH directions: a stolen access/refresh token can
    never impersonate the step-up handshake state."""
    for kind in (TokenKind.access, TokenKind.refresh):
        token = create_token(user_id=uuid4(), role="clinician", kind=kind, secret=SECRET)
        with pytest.raises(AuthError, match="mfa_pending"):
            decode_token(token, secret=SECRET, expected_kind=TokenKind.mfa_pending)


def test_mfa_pending_token_ttl_is_short() -> None:
    """The step-up window is minutes, not days: an mfa_pending token minted an hour
    ago is already dead."""
    token = create_token(
        user_id=uuid4(),
        role="clinician",
        kind=TokenKind.mfa_pending,
        secret=SECRET,
        now=datetime.now(UTC) - timedelta(hours=1),
    )
    with pytest.raises(AuthError, match="expired"):
        decode_token(token, secret=SECRET, expected_kind=TokenKind.mfa_pending)
