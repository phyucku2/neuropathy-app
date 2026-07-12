"""Auth service — registration, login, refresh (ADR-0010).

Users live behind the injected `UserRepository` (in-memory by default, so unit tests
and DB-less development keep working; Postgres in deployment). Token verification
itself is stateless JWT. The public methods are synchronous — they drive the
repository via `resolve_now`, which the in-memory store satisfies; the DB-backed
request path awaits the repository when the API layer moves onto the async session.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field

from app.core.security import (
    TokenKind,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import UserRole
from app.repositories.support import resolve_now
from app.repositories.user import InMemoryUserRepository, UserRecord, UserRepository

__all__ = ["AuthApiError", "AuthService", "TokenPair", "UserRecord"]


class AuthApiError(Exception):
    """Auth flow error the route layer maps to an HTTP response."""

    def __init__(self, reason: str, status_code: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


@dataclass
class AuthService:
    # Ephemeral random default: no hard-coded secret; dev sessions just don't survive
    # restarts unless JWT_SECRET is configured (ADR-0010).
    secret: str = field(default_factory=lambda: secrets.token_urlsafe(48))
    users: UserRepository = field(default_factory=InMemoryUserRepository)

    def register_patient(self, *, email: str, password: str, display_name: str) -> UserRecord:
        normalized = email.strip().lower()
        if resolve_now(self.users.get_by_email(normalized)) is not None:
            raise AuthApiError("An account with this email already exists", status_code=409)
        user = UserRecord(
            id=uuid.uuid4(),
            email=normalized,
            password_hash=hash_password(password),
            display_name=display_name,
            role=UserRole.patient,
            patient_id=uuid.uuid4(),  # DB layer will create the Patient row atomically
        )
        resolve_now(self.users.add(user))
        return user

    def login(self, *, email: str, password: str) -> tuple[UserRecord, TokenPair]:
        user = resolve_now(self.users.get_by_email(email.strip().lower()))
        # Same error for unknown email and wrong password — no account enumeration.
        if user is None or not verify_password(user.password_hash, password):
            raise AuthApiError("Invalid email or password", status_code=401)
        return user, self._issue_tokens(user)

    def refresh(self, *, refresh_token: str) -> str:
        claims = decode_token(refresh_token, secret=self.secret, expected_kind=TokenKind.refresh)
        user = resolve_now(self.users.get_by_id(claims.user_id))
        if user is None:
            raise AuthApiError("Account no longer exists", status_code=401)
        return create_token(
            user_id=user.id, role=user.role.value, kind=TokenKind.access, secret=self.secret
        )

    def get_user(self, user_id: uuid.UUID) -> UserRecord | None:
        return resolve_now(self.users.get_by_id(user_id))

    def _issue_tokens(self, user: UserRecord) -> TokenPair:
        return TokenPair(
            access_token=create_token(
                user_id=user.id, role=user.role.value, kind=TokenKind.access, secret=self.secret
            ),
            refresh_token=create_token(
                user_id=user.id, role=user.role.value, kind=TokenKind.refresh, secret=self.secret
            ),
        )
