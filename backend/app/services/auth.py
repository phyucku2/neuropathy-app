"""Auth service — registration, login, refresh (ADR-0010).

Users live behind the injected `UserRepository` (in-memory by default, so unit tests
and DB-less development keep working; Postgres in deployment). Token verification
itself is stateless JWT. All methods are async so any repository implementation
(in-memory or Postgres) works behind them.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.security import (
    TokenKind,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import UserRole
from app.repositories.user import (
    DuplicateEmailError,
    InMemoryUserRepository,
    OpsAlreadyExistsError,
    OpsDeactivateResult,
    UserRecord,
    UserRepository,
)

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

    async def register_patient(self, *, email: str, password: str, display_name: str) -> UserRecord:
        normalized = email.strip().lower()
        user = UserRecord(
            id=uuid.uuid4(),
            email=normalized,
            password_hash=hash_password(password),
            display_name=display_name,
            role=UserRole.patient,
            patient_id=uuid.uuid4(),
        )
        try:
            # The repository owns email uniqueness (atomic in Postgres via the unique
            # index) and creates the linked Patient row with the user.
            await self.users.add(user)
        except DuplicateEmailError as exc:
            raise AuthApiError(
                "An account with this email already exists", status_code=409
            ) from exc
        return user

    async def create_clinician(
        self, *, email: str, password: str, display_name: str, clinic_id: uuid.UUID
    ) -> UserRecord:
        """Provision a clinician account bound to its clinic (ADR-0010: clinician
        accounts are provisioned, never self-registered). Mirrors patient
        registration — Argon2id hash, repository-owned email uniqueness — but links
        a clinic instead of creating a Patient record."""
        normalized = email.strip().lower()
        user = UserRecord(
            id=uuid.uuid4(),
            email=normalized,
            password_hash=hash_password(password),
            display_name=display_name,
            role=UserRole.clinician,
            patient_id=None,
            clinic_id=clinic_id,
        )
        try:
            await self.users.add(user)
        except DuplicateEmailError as exc:
            raise AuthApiError(
                "An account with this email already exists", status_code=409
            ) from exc
        return user

    async def create_ops(self, *, email: str, password: str, display_name: str) -> UserRecord:
        """Provision an ops operator principal (ADR-0019): role=ops, carrying NEITHER
        a Patient record NOR a clinic. Mirrors clinician provisioning — Argon2id hash,
        repository-owned email uniqueness — so the whole login/JWT stack is reused; an
        ops JWT simply carries role=ops. Operators provision clinicians and other ops
        accounts, with per-operator identity, attribution, and revocation the shared
        bootstrap token never had."""
        normalized = email.strip().lower()
        user = UserRecord(
            id=uuid.uuid4(),
            email=normalized,
            password_hash=hash_password(password),
            display_name=display_name,
            role=UserRole.ops,
            patient_id=None,
            clinic_id=None,
        )
        try:
            await self.users.add(user)
        except DuplicateEmailError as exc:
            raise AuthApiError(
                "An account with this email already exists", status_code=409
            ) from exc
        return user

    async def create_first_ops(self, *, email: str, password: str, display_name: str) -> UserRecord:
        """Provision the FIRST ops operator on the bootstrap path (ADR-0019).

        Same account shape as create_ops, but inserted through the atomically-guarded
        `add_first_ops`: two concurrent first-ops bootstraps (distinct emails, so the
        email unique index would not stop them) serialize, exactly one wins, and the
        loser gets a 409 — the single documented "first operator" invariant holds even
        under a race. Steady-state creation still uses create_ops."""
        normalized = email.strip().lower()
        user = UserRecord(
            id=uuid.uuid4(),
            email=normalized,
            password_hash=hash_password(password),
            display_name=display_name,
            role=UserRole.ops,
            patient_id=None,
            clinic_id=None,
        )
        try:
            await self.users.add_first_ops(user)
        except DuplicateEmailError as exc:
            raise AuthApiError(
                "An account with this email already exists", status_code=409
            ) from exc
        except OpsAlreadyExistsError as exc:
            raise AuthApiError("An ops account already exists", status_code=409) from exc
        return user

    async def ops_account_exists(self) -> bool:
        """Whether ANY ops account exists (active or deactivated). Once true the
        first-ops bootstrap gate is closed for good (ADR-0019)."""
        return await self.users.count_with_role(UserRole.ops) > 0

    async def active_ops_count(self) -> int:
        """How many ops accounts are still active — the last-active-ops deactivation
        guard reads this (ADR-0019)."""
        return await self.users.count_with_role(UserRole.ops, active_only=True)

    async def deactivate_ops(self, user_id: uuid.UUID) -> UserRecord | None:
        """Revoke one operator (ADR-0019): flip active off and stamp disabled_at. A
        deactivated ops fails login and require_ops immediately. Returns the updated
        record, or None when no such account exists. Rotating one operator never
        touches the others — the shared token could not do this."""
        return await self.users.set_active(user_id, active=False, disabled_at=datetime.now(UTC))

    async def deactivate_ops_guarded(self, user_id: uuid.UUID) -> OpsDeactivateResult:
        """Atomic, last-active-ops-safe deactivation (ADR-0019): the count and the flip
        happen under one lock so two concurrent deactivations cannot both pass the >1
        guard and drive active ops to zero (a permanent provisioning lockout). The
        route maps the outcome to 404 / idempotent-200 / 409 / 200."""
        return await self.users.deactivate_ops_guarded(user_id, disabled_at=datetime.now(UTC))

    async def reactivate_ops(self, user_id: uuid.UUID) -> UserRecord | None:
        """Restore a deactivated operator (ADR-0019 defense-in-depth): flip active on
        and clear disabled_at so an accidental over-deactivation is recoverable without
        DB surgery. Returns the updated record, or None when no such account exists.
        Reactivation only ever ADDS an active operator, so it needs no lockout guard."""
        return await self.users.set_active(user_id, active=True, disabled_at=None)

    async def login(self, *, email: str, password: str) -> tuple[UserRecord, TokenPair]:
        user = await self.users.get_by_email(email.strip().lower())
        # Same error for unknown email, deactivated account, and wrong password — a
        # disabled operator (or any disabled account) is indistinguishable from a
        # nonexistent one, no enumeration (ADR-0019).
        if user is None or not user.active or not verify_password(user.password_hash, password):
            raise AuthApiError("Invalid email or password", status_code=401)
        return user, self._issue_tokens(user)

    async def refresh(self, *, refresh_token: str) -> str:
        claims = decode_token(refresh_token, secret=self.secret, expected_kind=TokenKind.refresh)
        user = await self.users.get_by_id(claims.user_id)
        # Re-check active, mirroring login(): a deactivated account must not keep minting
        # fresh access tokens for its refresh token's whole lifetime — that would defeat
        # revocation-within-one-TTL (ADR-0019). A deactivated account is indistinguishable
        # from a deleted one here, same 401, no enumeration.
        if user is None or not user.active:
            raise AuthApiError("Account no longer exists", status_code=401)
        return create_token(
            user_id=user.id, role=user.role.value, kind=TokenKind.access, secret=self.secret
        )

    async def get_user(self, user_id: uuid.UUID) -> UserRecord | None:
        return await self.users.get_by_id(user_id)

    def _issue_tokens(self, user: UserRecord) -> TokenPair:
        return TokenPair(
            access_token=create_token(
                user_id=user.id, role=user.role.value, kind=TokenKind.access, secret=self.secret
            ),
            refresh_token=create_token(
                user_id=user.id, role=user.role.value, kind=TokenKind.refresh, secret=self.secret
            ),
        )
