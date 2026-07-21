"""MFA (TOTP) service — enrollment and the login step-up (readiness plan §1B C6).

Privileged principals (clinician/ops) enroll an authenticator app: the TOTP secret is
minted here, stored ONLY behind the SecretStore seam (Fernet-encrypted at rest in
Postgres when SECRET_STORE_KEY is configured — the same vault EMR OAuth tokens use,
ADR-0017; never plaintext in the database), and returned exactly once as an
``otpauth://`` URI for the authenticator to scan. A factor counts only after the user
confirms it with a matching code (`confirmed_at`), so an abandoned enrollment can
never lock an account out.

Login step-up: a confirmed factor turns password success into a short-lived
``mfa_pending`` token — a DISTINCT JWT kind (app/core/security.py) that the kind check
makes useless as an access or refresh token — and POST /auth/mfa/verify exchanges it
plus the 6-digit code for the real tokens. Wrong codes are audited and throttled per
token-subject sentinel (the §1B C5 limiter pattern; audited refusals are RETURNED so
their rows commit — docs/lessons.md "return don't raise").

Patients are completely unaffected: they can never enroll, and their login never
steps up. `settings.mfa_required_for_privileged` (default False) is the go-live
enforcement flag — flag-off keeps unenrolled privileged logins exactly as today;
flag-on refuses them with an enrollment-required response.

Account deletion (ADR-0027) needs no factor-erasure step: deletion is patient-only
(require_patient + the service's own role check), and patients can never hold a
factor — there is no clinician/ops account-deletion flow to wire into.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.security import TokenKind, create_token, decode_token
from app.core.totp import generate_totp_secret, otpauth_uri, verify_totp
from app.emr.service import InMemorySecretStore, SecretStore
from app.models.audit import AuditEvent
from app.models.user import UserRole
from app.repositories.audit import AuditEventRepository, InMemoryAuditEventRepository
from app.repositories.mfa import InMemoryMfaFactorRepository, MfaFactorRepository
from app.repositories.user import InMemoryUserRepository, UserRecord, UserRepository
from app.services.auth import LOGIN_RATE_LIMITED_DETAIL, LoginDenied, TokenPair
from app.services.rate_limit import SlidingWindowRateLimiter

__all__ = [
    "MFA_ENROLLMENT_REQUIRED_DETAIL",
    "MFA_ISSUER",
    "WRONG_CODE_DETAIL",
    "MfaApiError",
    "MfaEnrollment",
    "MfaEnrollmentRequired",
    "MfaService",
    "MfaStepUpRequired",
    "mfa_verify_rate_limiter",
    "mfa_verify_throttle_actor_id",
]

# The label authenticator apps show next to the account (Key Uri Format issuer).
MFA_ISSUER = "Neuropathy"

# One message for a wrong code, a missing/unconfirmed factor, and a vanished account —
# a signature-valid pending token learns nothing beyond "the step-up failed" (the
# password already cleared, so this only ever re-blames the code). Surfaced verbatim
# by the login UI's step-up screen.
WRONG_CODE_DETAIL = "Invalid code"

# The flag-on refusal for unenrolled privileged logins (settings-gated, 403): names
# the fix, never the account state beyond what the caller — who just proved the
# password — is entitled to know.
MFA_ENROLLMENT_REQUIRED_DETAIL = (
    "Multi-factor authentication enrollment is required for this account. "
    "Sign-in is disabled until an authenticator app is enrolled."
)

# Step-up verification sentinel namespace (§1B C5/C6): wrong-code audit rows key on a
# uuid5 of the token-subject hash, mirroring the refresh throttle — never the raw id.
_MFA_VERIFY_THROTTLE_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "urn:neuropathy-app:mfa-verify-throttle"
)


def mfa_verify_throttle_actor_id(user_id: uuid.UUID) -> uuid.UUID:
    """The step-up throttle sentinel: uuid5 of the token-subject hash (subjects only
    ever come from signature-valid mfa_pending tokens, so the sentinel space is not
    attacker-minted)."""
    digest = hashlib.sha256(str(user_id).encode()).hexdigest()
    return uuid.uuid5(_MFA_VERIFY_THROTTLE_NAMESPACE, digest)


def mfa_verify_rate_limiter(counter: AuditEventRepository) -> SlidingWindowRateLimiter:
    """The step-up code throttle (§1B C6 via the C5 limiter): counts the
    'mfa_verify_failed' audit events wrong codes write, on the LOGIN budget — a
    6-digit code deserves no more guesses than a password. Over the budget the answer
    is 429 BEFORE the code is even compared."""
    return SlidingWindowRateLimiter(
        counter=counter,
        action="mfa_verify_failed",
        max_events=settings.login_rate_limit_max,
        window=timedelta(seconds=settings.login_rate_limit_window_seconds),
    )


class MfaApiError(Exception):
    """MFA flow error the route layer maps to an HTTP response.

    Raised ONLY on paths that have written nothing (wrong role, missing factor,
    wrong confirmation code), so the resulting HTTPException has nothing to roll
    back. Audited step-up refusals are `LoginDenied`, returned instead.
    """

    def __init__(self, reason: str, status_code: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


@dataclass(frozen=True)
class MfaEnrollment:
    """The one-time enrollment payload: shown once, never re-readable — the server
    keeps only the vault-encrypted copy."""

    otpauth_uri: str
    secret: str


@dataclass(frozen=True)
class MfaStepUpRequired:
    """Password success for an enrolled privileged account: the 6-digit code is
    still owed, and this short-lived mfa_pending token is the only thing issued."""

    mfa_pending_token: str


@dataclass(frozen=True)
class MfaEnrollmentRequired:
    """Flag-on refusal: an unenrolled privileged account may not complete login."""

    reason: str


@dataclass
class MfaService:
    """TOTP enrollment + login step-up over the injected stores (§1B C6).

    `secret` MUST be the same JWT signing secret the AuthService uses — the
    mfa_pending token minted at login is decoded here at verification (deps wires
    both from the one process secret).
    """

    secret: str
    users: UserRepository = field(default_factory=InMemoryUserRepository)
    factors: MfaFactorRepository = field(default_factory=InMemoryMfaFactorRepository)
    secret_store: SecretStore = field(default_factory=InMemorySecretStore)
    audit: AuditEventRepository = field(default_factory=InMemoryAuditEventRepository)

    async def enrolled(self, user_id: uuid.UUID) -> bool:
        """Whether this user holds a CONFIRMED factor (pending ones don't count)."""
        factor = await self.factors.get_for_user(user_id)
        return factor is not None and factor.confirmed_at is not None

    async def enroll(self, *, user_id: uuid.UUID) -> MfaEnrollment:
        """Start (or restart) enrollment for a privileged account.

        Mints a fresh TOTP secret, vaults it via the SecretStore seam (encrypted at
        rest — never plaintext in the DB, ADR-0017), and REPLACES any existing factor
        with a fresh unconfirmed one; the superseded vault entry is purged through
        the same delete seam revocation uses. Returns the otpauth:// URI + secret for
        the single showing.
        """
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise MfaApiError("Account no longer exists", status_code=401)
        if user.role is UserRole.patient:
            # Defense in depth behind the route's require_privileged gate: patients
            # never hold a factor (§1B C6 — patients completely unaffected).
            raise MfaApiError("Clinician or ops account required", status_code=403)
        totp_secret = generate_totp_secret()
        ref = await self.secret_store.put({"totp_secret": totp_secret})
        superseded = await self.factors.replace_for_user(user.id, secret_ref=ref)
        if superseded is not None:
            await self.secret_store.delete(superseded)
        await self.audit.add(
            AuditEvent(
                actor_id=user.id,
                actor_role=user.role.value,
                action="mfa_enroll",
                patient_id=None,
                # References/shape only — never the secret or its vault ref value.
                detail={"replaced_existing_factor": superseded is not None},
            )
        )
        return MfaEnrollment(
            otpauth_uri=otpauth_uri(totp_secret, account_name=user.email, issuer=MFA_ISSUER),
            secret=totp_secret,
        )

    async def confirm_enrollment(self, *, user_id: uuid.UUID, code: str) -> None:
        """Activate the pending factor by proving the authenticator holds the secret.

        Wrong codes are 401 (`WRONG_CODE_DETAIL`) and write nothing — the caller is
        authenticated and was just shown the secret, so guessing here is pointless
        and needs no throttle. A matching code stamps confirmed_at (idempotent) and
        audits the activation.
        """
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise MfaApiError("Account no longer exists", status_code=401)
        factor = await self.factors.get_for_user(user_id)
        if factor is None:
            raise MfaApiError("No enrollment in progress", status_code=409)
        vaulted = await self.secret_store.get(factor.secret_ref)
        if vaulted is None:
            # The vault entry is gone (e.g. a keyless-vault restart): the enrollment
            # can never be confirmed — fail closed and have the user start over.
            raise MfaApiError("Enrollment is no longer valid — start again", status_code=409)
        now = datetime.now(UTC)
        if not verify_totp(vaulted["totp_secret"], code, at=now):
            raise MfaApiError(WRONG_CODE_DETAIL, status_code=401)
        await self.factors.confirm(user_id, at=now)
        await self.audit.add(
            AuditEvent(
                actor_id=user.id,
                actor_role=user.role.value,
                action="mfa_activate",
                patient_id=None,
                detail={},
            )
        )

    async def login_step_up(
        self, user: UserRecord
    ) -> MfaStepUpRequired | MfaEnrollmentRequired | None:
        """The post-password decision for /auth/login (§1B C6).

        Patients: always None — their flow is byte-identical to today. Privileged
        principals: a confirmed factor yields the mfa_pending step-up (full tokens
        are withheld); no confirmed factor is None (today's behavior) unless
        `mfa_required_for_privileged` is on, which refuses with enrollment-required.
        """
        if user.role is UserRole.patient:
            return None
        if await self.enrolled(user.id):
            return MfaStepUpRequired(
                mfa_pending_token=create_token(
                    user_id=user.id,
                    role=user.role.value,
                    kind=TokenKind.mfa_pending,
                    secret=self.secret,
                )
            )
        if settings.mfa_required_for_privileged:
            return MfaEnrollmentRequired(reason=MFA_ENROLLMENT_REQUIRED_DETAIL)
        return None

    async def verify_login(self, *, mfa_pending_token: str, code: str) -> TokenPair | LoginDenied:
        """Exchange the pending token + a matching code for the real tokens.

        The decode enforces kind=mfa_pending (an access/refresh token is refused
        here exactly as a pending token is refused everywhere else — AuthError, the
        route's 401, nothing written). The throttle fires BEFORE the code is
        compared; every refusal past it is a RETURNED `LoginDenied` whose PHI-free
        audit event commits with the request (docs/lessons.md). Wrong code, missing/
        unconfirmed factor, and a vanished/deactivated account are one identical
        audited 401.
        """
        claims = decode_token(
            mfa_pending_token, secret=self.secret, expected_kind=TokenKind.mfa_pending
        )
        now = datetime.now(UTC)
        actor = mfa_verify_throttle_actor_id(claims.user_id)
        if not await mfa_verify_rate_limiter(self.audit).allow(actor, now=now):
            return LoginDenied(LOGIN_RATE_LIMITED_DETAIL, status_code=429)
        user = await self.users.get_by_id(claims.user_id)
        factor = None if user is None else await self.factors.get_for_user(claims.user_id)
        vaulted = None if factor is None else await self.secret_store.get(factor.secret_ref)
        if (
            user is None
            or not user.active
            or factor is None
            or factor.confirmed_at is None
            or vaulted is None
            or not verify_totp(vaulted["totp_secret"], code, at=now)
        ):
            return await self._deny_verify(actor)
        await self.audit.add(
            AuditEvent(
                actor_id=user.id,
                actor_role=user.role.value,
                action="mfa_verify",
                patient_id=None,
                detail={},
            )
        )
        return TokenPair(
            access_token=create_token(
                user_id=user.id, role=user.role.value, kind=TokenKind.access, secret=self.secret
            ),
            refresh_token=create_token(
                user_id=user.id, role=user.role.value, kind=TokenKind.refresh, secret=self.secret
            ),
        )

    async def _deny_verify(self, actor: uuid.UUID) -> LoginDenied:
        """One bounded, PHI-free 'mfa_verify_failed' event per refusal — exactly the
        rows the step-up throttle counts, so their volume is capped by its budget."""
        await self.audit.add(
            AuditEvent(
                actor_id=actor,
                actor_role="system",
                action="mfa_verify_failed",
                patient_id=None,
                detail={
                    "limit": settings.login_rate_limit_max,
                    "window_seconds": settings.login_rate_limit_window_seconds,
                },
            )
        )
        return LoginDenied(WRONG_CODE_DETAIL, status_code=401)
