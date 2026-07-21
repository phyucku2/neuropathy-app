"""Auth service — registration, login, refresh (ADR-0010).

Users live behind the injected `UserRepository` (in-memory by default, so unit tests
and DB-less development keep working; Postgres in deployment). Token verification
itself is stateless JWT. All methods are async so any repository implementation
(in-memory or Postgres) works behind them.

Login and refresh are throttled (readiness plan §1B C5, the ADR-0017 sliding-window
pattern): failed attempts are audited under NON-ENUMERATING sentinel actors — a uuid5
of the normalized-email hash for login, a uuid5 of the token-subject hash for refresh;
the raw email/subject never keys anything — and over the window budget the answer is
429 BEFORE the Argon2id verify (login) or the repository lookup (refresh) runs, so the
limiter caps both the credential oracle and its CPU cost. Audited refusals are
RETURNED (`LoginDenied`), never raised: their audit rows must commit with the request
transaction (docs/lessons.md "return don't raise").
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.security import (
    TokenKind,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.audit import AuditEvent
from app.models.user import UserRole
from app.repositories.audit import AuditEventRepository, InMemoryAuditEventRepository
from app.repositories.user import (
    DuplicateEmailError,
    InMemoryUserRepository,
    OpsAlreadyExistsError,
    OpsDeactivateResult,
    UserRecord,
    UserRepository,
)
from app.services.rate_limit import SlidingWindowRateLimiter

__all__ = [
    "INVALID_CREDENTIALS_DETAIL",
    "LOGIN_RATE_LIMITED_DETAIL",
    "AuthApiError",
    "AuthService",
    "LoginDenied",
    "TokenPair",
    "UserRecord",
    "login_rate_limiter",
    "login_throttle_actor_id",
    "rate_limited_audit_limiter",
    "refresh_rate_limiter",
    "refresh_throttle_actor_id",
]

# One message for unknown email, deactivated account, and wrong password — no account
# enumeration (ADR-0019). Surfaced verbatim by the login UI.
INVALID_CREDENTIALS_DETAIL = "Invalid email or password"

# Over the failed-attempt budget (§1B C5): friendly and PHI-free, and deliberately the
# SAME for a probed unknown email and a real account — a 429 carries zero information
# about whether the email matches anything.
LOGIN_RATE_LIMITED_DETAIL = "Too many attempts right now — please try again in a little while."

# Sentinel namespaces (§1B C5): throttle actors are uuid5 digests, so the audit table
# never keys a row on a raw email address or token subject. One namespace per surface —
# a login-failure burst can never spend the refresh budget or vice versa.
_LOGIN_THROTTLE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "urn:neuropathy-app:login-throttle")
_REFRESH_THROTTLE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "urn:neuropathy-app:refresh-throttle")


def login_throttle_actor_id(email: str) -> uuid.UUID:
    """The non-enumerating login-throttle sentinel: uuid5 of the normalized-email
    hash. Deterministic per email (so a guessing campaign against one account shares
    one budget) yet one-way — the email is never recoverable from the audit row."""
    digest = hashlib.sha256(email.strip().lower().encode()).hexdigest()
    return uuid.uuid5(_LOGIN_THROTTLE_NAMESPACE, digest)


def refresh_throttle_actor_id(user_id: uuid.UUID) -> uuid.UUID:
    """The refresh-throttle sentinel: uuid5 of the token-subject hash (subjects only
    ever come from signature-valid tokens, so the sentinel space is not attacker-
    minted; garbage tokens are rejected at decode and never audited)."""
    digest = hashlib.sha256(str(user_id).encode()).hexdigest()
    return uuid.uuid5(_REFRESH_THROTTLE_NAMESPACE, digest)


def login_rate_limiter(counter: AuditEventRepository) -> SlidingWindowRateLimiter:
    """The settings-driven login throttle (§1B C5), counting the 'login_failed' audit
    events the refusal path writes — one per failed attempt that reached the lookup/
    verify. Over-budget attempts answer 429 BEFORE the Argon2id verify (or any
    repository lookup) and never count, so the budget frees up as the window slides."""
    return SlidingWindowRateLimiter(
        counter=counter,
        action="login_failed",
        max_events=settings.login_rate_limit_max,
        window=timedelta(seconds=settings.login_rate_limit_window_seconds),
    )


def refresh_rate_limiter(counter: AuditEventRepository) -> SlidingWindowRateLimiter:
    """The settings-driven refresh throttle (§1B C5), counting 'refresh_failed' audit
    events — one per signature-valid refresh whose account lookup failed. Healthy
    refreshes never count."""
    return SlidingWindowRateLimiter(
        counter=counter,
        action="refresh_failed",
        max_events=settings.refresh_rate_limit_max,
        window=timedelta(seconds=settings.refresh_rate_limit_window_seconds),
    )


def rate_limited_audit_limiter(
    counter: AuditEventRepository, *, max_events: int, window_seconds: int
) -> SlidingWindowRateLimiter:
    """Cap on 'login_rate_limited' audit WRITES per sentinel actor (the
    bootstrap_denied pattern, ADR-0017): the throttled surfaces are unauthenticated,
    so unbounded per-429 audit rows would hand an anonymous client a log-flood
    primitive. Beyond the cap the identical 429 still answers; only the write is
    skipped. Reuses the surface's own budget/window — no extra knob to drift."""
    return SlidingWindowRateLimiter(
        counter=counter,
        action="login_rate_limited",
        max_events=max_events,
        window=timedelta(seconds=window_seconds),
    )


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


@dataclass(frozen=True)
class LoginDenied:
    """Audited login/refresh refusal the route must RETURN as a response, never
    raise: its 'login_failed' / 'refresh_failed' / 'login_rate_limited' audit event
    has to commit with the request transaction, and a raised HTTPException would roll
    it back (docs/lessons.md "return don't raise") — the throttle that counts those
    events would then never trip."""

    reason: str
    status_code: int


@dataclass
class AuthService:
    # Ephemeral random default: no hard-coded secret; dev sessions just don't survive
    # restarts unless JWT_SECRET is configured (ADR-0010).
    secret: str = field(default_factory=lambda: secrets.token_urlsafe(48))
    users: UserRepository = field(default_factory=InMemoryUserRepository)
    # Login/refresh throttle counter + PHI-free failure events (§1B C5). In DB mode
    # this is the request-scoped Postgres audit repository (deps wiring), so the
    # counter is exactly as durable as the audit trail itself.
    audit: AuditEventRepository = field(default_factory=InMemoryAuditEventRepository)

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

    async def create_caregiver(self, *, email: str, password: str, display_name: str) -> UserRecord:
        """Create a caregiver principal (ADR-0047): role=caregiver, carrying NEITHER
        a Patient record NOR a clinic — the ops account shape with a different role.
        Mirrors create_ops — Argon2id hash, repository-owned email uniqueness — so
        the whole login/JWT stack is reused; a caregiver JWT simply carries
        role=caregiver. NOT self-service on its own: the route only calls this with
        a validated invite code in hand (self-registration ONLY with a valid code),
        or never — caregivers cannot exist outside the invite-claim flow."""
        normalized = email.strip().lower()
        user = UserRecord(
            id=uuid.uuid4(),
            email=normalized,
            password_hash=hash_password(password),
            display_name=display_name,
            role=UserRole.caregiver,
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

    async def login(
        self, *, email: str, password: str
    ) -> tuple[UserRecord, TokenPair] | LoginDenied:
        """Password login, throttled per email sentinel (§1B C5).

        Success returns the user + tokens; every refusal is a RETURNED `LoginDenied`
        (its audit event must commit — docs/lessons.md). The throttle fires FIRST,
        before the email is even looked up, so over the budget the answer is 429
        regardless of the password offered — the oracle and its Argon2id CPU are both
        capped, and a 429 reveals nothing about whether the email matches an account.
        """
        now = datetime.now(UTC)
        actor = login_throttle_actor_id(email)
        if not await login_rate_limiter(self.audit).allow(actor, now=now):
            await self._audit_rate_limited(
                actor,
                surface="login",
                now=now,
                max_events=settings.login_rate_limit_max,
                window_seconds=settings.login_rate_limit_window_seconds,
            )
            return LoginDenied(LOGIN_RATE_LIMITED_DETAIL, status_code=429)
        user = await self.users.get_by_email(email.strip().lower())
        # Same refusal for unknown email, deactivated account, and wrong password — a
        # disabled operator (or any disabled account) is indistinguishable from a
        # nonexistent one, no enumeration (ADR-0019). All three write the SAME
        # PHI-free 'login_failed' event under the email sentinel (counts/config only,
        # never the email), so they are indistinguishable in the audit trail too.
        if user is None or not user.active or not verify_password(user.password_hash, password):
            await self.audit.add(
                AuditEvent(
                    actor_id=actor,
                    actor_role="system",
                    action="login_failed",
                    patient_id=None,
                    detail={
                        "limit": settings.login_rate_limit_max,
                        "window_seconds": settings.login_rate_limit_window_seconds,
                    },
                )
            )
            return LoginDenied(INVALID_CREDENTIALS_DETAIL, status_code=401)
        return user, self._issue_tokens(user)

    async def refresh(self, *, refresh_token: str) -> str | LoginDenied:
        """Mint a fresh access token, throttled per token-subject sentinel (§1B C5).

        A garbage/expired/wrong-kind token raises AuthError from the decode — nothing
        has been written, so the route maps it to 401 directly. Only signature-valid
        tokens reach the throttle (the sentinel space is therefore not attacker-
        minted), which fires BEFORE the repository lookup; audited refusals are
        RETURNED (docs/lessons.md).
        """
        claims = decode_token(refresh_token, secret=self.secret, expected_kind=TokenKind.refresh)
        now = datetime.now(UTC)
        actor = refresh_throttle_actor_id(claims.user_id)
        if not await refresh_rate_limiter(self.audit).allow(actor, now=now):
            await self._audit_rate_limited(
                actor,
                surface="refresh",
                now=now,
                max_events=settings.refresh_rate_limit_max,
                window_seconds=settings.refresh_rate_limit_window_seconds,
            )
            return LoginDenied(LOGIN_RATE_LIMITED_DETAIL, status_code=429)
        user = await self.users.get_by_id(claims.user_id)
        # Re-check active, mirroring login(): a deactivated account must not keep minting
        # fresh access tokens for its refresh token's whole lifetime — that would defeat
        # revocation-within-one-TTL (ADR-0019). A deactivated account is indistinguishable
        # from a deleted one here, same 401, no enumeration.
        if user is None or not user.active:
            await self.audit.add(
                AuditEvent(
                    actor_id=actor,
                    actor_role="system",
                    action="refresh_failed",
                    patient_id=None,
                    detail={
                        "limit": settings.refresh_rate_limit_max,
                        "window_seconds": settings.refresh_rate_limit_window_seconds,
                    },
                )
            )
            return LoginDenied("Account no longer exists", status_code=401)
        return create_token(
            user_id=user.id, role=user.role.value, kind=TokenKind.access, secret=self.secret
        )

    async def _audit_rate_limited(
        self,
        actor: uuid.UUID,
        *,
        surface: str,
        now: datetime,
        max_events: int,
        window_seconds: int,
    ) -> None:
        """One bounded, PHI-free 'login_rate_limited' event per refusal — capped per
        sentinel actor (the bootstrap_denied pattern) so the unauthenticated 429 path
        can never flood the audit table; beyond the cap only the write is skipped."""
        capped = rate_limited_audit_limiter(
            self.audit, max_events=max_events, window_seconds=window_seconds
        )
        if await capped.allow(actor, now=now):
            await self.audit.add(
                AuditEvent(
                    actor_id=actor,
                    actor_role="system",
                    action="login_rate_limited",
                    patient_id=None,
                    # Counts/config only — never the email or subject (audit contract).
                    detail={
                        "surface": surface,
                        "limit": max_events,
                        "window_seconds": window_seconds,
                    },
                )
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
