"""Auth service — registration, login, refresh (ADR-0010).

In-memory user repository behind the same shape the DB-backed store will use (same
posture as the EMR service). Token verification itself is stateless JWT.
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


class AuthApiError(Exception):
    """Auth flow error the route layer maps to an HTTP response."""

    def __init__(self, reason: str, status_code: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


@dataclass
class UserRecord:
    """In-memory twin of models.User."""

    id: uuid.UUID
    email: str
    password_hash: str
    display_name: str
    role: UserRole
    patient_id: uuid.UUID | None


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


@dataclass
class AuthService:
    # Ephemeral random default: no hard-coded secret; dev sessions just don't survive
    # restarts unless JWT_SECRET is configured (ADR-0010).
    secret: str = field(default_factory=lambda: secrets.token_urlsafe(48))
    _by_email: dict[str, UserRecord] = field(default_factory=dict)
    _by_id: dict[uuid.UUID, UserRecord] = field(default_factory=dict)

    def register_patient(self, *, email: str, password: str, display_name: str) -> UserRecord:
        normalized = email.strip().lower()
        if normalized in self._by_email:
            raise AuthApiError("An account with this email already exists", status_code=409)
        user = UserRecord(
            id=uuid.uuid4(),
            email=normalized,
            password_hash=hash_password(password),
            display_name=display_name,
            role=UserRole.patient,
            patient_id=uuid.uuid4(),  # DB layer will create the Patient row atomically
        )
        self._by_email[normalized] = user
        self._by_id[user.id] = user
        return user

    def login(self, *, email: str, password: str) -> tuple[UserRecord, TokenPair]:
        user = self._by_email.get(email.strip().lower())
        # Same error for unknown email and wrong password — no account enumeration.
        if user is None or not verify_password(user.password_hash, password):
            raise AuthApiError("Invalid email or password", status_code=401)
        return user, self._issue_tokens(user)

    def refresh(self, *, refresh_token: str) -> str:
        claims = decode_token(refresh_token, secret=self.secret, expected_kind=TokenKind.refresh)
        user = self._by_id.get(claims.user_id)
        if user is None:
            raise AuthApiError("Account no longer exists", status_code=401)
        return create_token(
            user_id=user.id, role=user.role.value, kind=TokenKind.access, secret=self.secret
        )

    def get_user(self, user_id: uuid.UUID) -> UserRecord | None:
        return self._by_id.get(user_id)

    def _issue_tokens(self, user: UserRecord) -> TokenPair:
        return TokenPair(
            access_token=create_token(
                user_id=user.id, role=user.role.value, kind=TokenKind.access, secret=self.secret
            ),
            refresh_token=create_token(
                user_id=user.id, role=user.role.value, kind=TokenKind.refresh, secret=self.secret
            ),
        )
