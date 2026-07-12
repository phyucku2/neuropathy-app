"""Password hashing and session tokens (ADR-0010) — pure and fully unit-tested.

Argon2id for passwords (OWASP first choice); short-lived HS256 JWT access tokens with
long-lived refresh tokens. Token *kind* is enforced so a refresh token can never be
replayed as an access token.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=30)

_hasher = PasswordHasher()  # argon2id with library defaults


class AuthError(Exception):
    """Authentication failure; routes map this to 401."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class TokenKind(enum.StrEnum):
    access = "access"
    refresh = "refresh"


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    role: str
    kind: TokenKind


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def create_token(
    *,
    user_id: uuid.UUID,
    role: str,
    kind: TokenKind,
    secret: str,
    now: datetime | None = None,
    ttl: timedelta | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    lifetime = ttl or (ACCESS_TOKEN_TTL if kind is TokenKind.access else REFRESH_TOKEN_TTL)
    payload = {
        "sub": str(user_id),
        "role": role,
        "kind": kind.value,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + lifetime).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, *, secret: str, expected_kind: TokenKind) -> TokenClaims:
    """Validate signature, expiry, and kind; return the claims or raise AuthError."""
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Token is invalid") from exc

    if payload.get("kind") != expected_kind.value:
        raise AuthError(f"Expected a {expected_kind.value} token")
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise AuthError("Token subject is invalid") from exc
    return TokenClaims(user_id=user_id, role=str(payload.get("role", "")), kind=expected_kind)
