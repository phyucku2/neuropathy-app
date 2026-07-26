"""Shared API dependencies — the authenticated current user (ADR-0010) and the
storage-mode-aware service providers.

Two storage modes, selected per request by `get_db_session` (app/db/session.py):

- **Postgres mode** (DATABASE_URL configured — the dependency yields a session):
  services are constructed per request on Postgres repositories bound to the
  request-scoped transaction. OAuth pending-auth states live in the DB-backed
  single-use store and — when SECRET_STORE_KEY is configured — OAuth tokens live in
  the encrypted-at-rest Postgres vault, so both survive restarts and multi-worker
  deployments (ADR-0017). Without a key the token vault stays the per-process
  in-memory singleton, fail closed: plaintext secrets never reach the database
  (tokens then don't survive restarts — configure the key). The JWT signing secret
  remains the process-level singleton below.
- **In-memory mode** (no DATABASE_URL — the dependency yields None): the lru_cache
  service singletons serve every request, exactly as before. Unit tests and DB-less
  development are unchanged, and tests keep overriding get_auth_service /
  get_emr_service directly.
"""

from __future__ import annotations

import json
import logging
import os
import secrets as pysecrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Any

from cryptography.fernet import Fernet
from fastapi import BackgroundTasks, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.narrative import AnthropicNarrator, AzureOpenAINarrator, Narrator
from app.core.config import settings
from app.core.errors import ErrorReporter, HttpErrorReporter
from app.core.security import AuthError, TokenKind, decode_token
from app.db.session import get_db_session
from app.emr.providers import TOP_PROVIDERS, client_id_for
from app.emr.service import (
    UNCONFIGURED_CLIENT_ID,
    EmrService,
    InMemoryPendingAuthStore,
    InMemorySecretStore,
    SecretStore,
)
from app.emr.signals import InMemoryNewChartNoteSink
from app.emr.transport import HttpxTransport
from app.ingestion.food import NullNutritionSource, NutritionSource
from app.models.user import UserRole
from app.repositories.capability import InMemoryCapabilityRepository
from app.repositories.caregiver import (
    InMemoryCaregiverInviteRepository,
    InMemoryCaregiverLinkRepository,
)
from app.repositories.caregiver_alert import (
    InMemoryCaregiverAlertPreferenceRepository,
    InMemoryCaregiverAlertRepository,
)
from app.repositories.caregiver_push_token import (
    CaregiverPushTokenRepository,
    InMemoryCaregiverPushTokenRepository,
)
from app.repositories.emr_clinical_note import InMemoryEmrClinicalNoteRepository
from app.repositories.mfa import InMemoryMfaFactorRepository
from app.repositories.patient_capability import InMemoryPatientCapabilityRepository
from app.repositories.postgres import (
    PostgresAuditEventRepository,
    PostgresCapabilityRepository,
    PostgresCaregiverAlertPreferenceRepository,
    PostgresCaregiverAlertRepository,
    PostgresCaregiverInviteRepository,
    PostgresCaregiverLinkRepository,
    PostgresCaregiverPushTokenRepository,
    PostgresClinicConnectionRepository,
    PostgresClinicRepository,
    PostgresEmrClinicalNoteRepository,
    PostgresEmrConnectionRepository,
    PostgresMfaFactorRepository,
    PostgresObservationRepository,
    PostgresPatientCapabilityRepository,
    PostgresPendingAuthStore,
    PostgresSecretStore,
    PostgresUserRepository,
)
from app.services.account_deletion import AccountDeletionService
from app.services.auth import AuthService
from app.services.capability import CapabilityService
from app.services.caregiver import CaregiverService
from app.services.caregiver_alert import CaregiverAlertService
from app.services.caregiver_push_dispatch import fan_out_caregiver_push
from app.services.clinic import ClinicService
from app.services.export import PatientDataExportService
from app.services.mfa import MfaService
from app.services.push import (
    FcmCredentialsError,
    FcmPushSender,
    HttpxPushTransport,
    PushMessage,
)

_bearer = HTTPBearer(auto_error=False)
_log = logging.getLogger(__name__)

# None = no database configured -> in-memory mode. The default lets tests (and the
# cached-singleton contract) call the providers directly, without a request.
DbSessionDep = Annotated[AsyncSession | None, Depends(get_db_session)]


@lru_cache(maxsize=1)
def _process_jwt_secret() -> str:
    """One signing secret per process, so every request-scoped AuthService verifies
    tokens its siblings issued. Configure JWT_SECRET for restart/multi-worker
    survival (ADR-0010); the fallback is ephemeral."""
    return settings.jwt_secret or pysecrets.token_urlsafe(48)


@lru_cache(maxsize=1)
def _default_auth_service() -> AuthService:
    # The audit store is the SAME singleton every other in-memory feature uses
    # (the EMR service owns it), so the login/refresh throttle (§1B C5) counts and
    # writes into the one shared trail.
    audit = _default_emr_service().audit
    if settings.jwt_secret:
        return AuthService(secret=settings.jwt_secret, audit=audit)
    return AuthService(audit=audit)  # ephemeral dev secret (ADR-0010)


def get_auth_service(session: DbSessionDep = None) -> AuthService:
    if session is None:
        return _default_auth_service()
    return AuthService(
        secret=_process_jwt_secret(),
        users=PostgresUserRepository(session),
        audit=PostgresAuditEventRepository(session),
    )


AuthDep = Annotated[AuthService, Depends(get_auth_service)]


@dataclass(frozen=True)
class CurrentUser:
    user_id: uuid.UUID
    role: UserRole
    patient_id: uuid.UUID | None
    email: str
    display_name: str
    # Set for clinician users (ADR-0012); defaulted last so existing constructions
    # keep working unchanged.
    clinic_id: uuid.UUID | None = None
    # Whether the account is active (ADR-0019). A live JWT can outlast a deactivation
    # by up to the access-token TTL, so the role gates re-check this, not just login.
    active: bool = True


def _unauthorized(reason: str) -> HTTPException:
    return HTTPException(status_code=401, detail=reason, headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    auth: AuthDep,
) -> CurrentUser:
    if credentials is None:
        raise _unauthorized("Missing bearer token")
    try:
        claims = decode_token(
            credentials.credentials, secret=auth.secret, expected_kind=TokenKind.access
        )
    except AuthError as exc:
        raise _unauthorized(exc.reason) from exc
    user = await auth.get_user(claims.user_id)
    if user is None:
        raise _unauthorized("Account no longer exists")
    # Revocation is enforced centrally here, at authentication, for EVERY role (ADR-0019):
    # a short-lived access token can outlive a deactivation by up to its TTL, so a
    # deactivated principal of any role — patient, clinician, or ops — is refused before
    # it reaches any endpoint or role gate. PHI-free reason, indistinguishable from a
    # deleted account.
    if not user.active:
        raise _unauthorized("Account is not active")
    return CurrentUser(
        user_id=user.id,
        role=user.role,
        patient_id=user.patient_id,
        email=user.email,
        display_name=user.display_name,
        clinic_id=user.clinic_id,
        active=user.active,
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_patient(current: CurrentUserDep) -> CurrentUser:
    """Patient-scoped endpoints: the caller must be a patient user with a record."""
    if current.role is not UserRole.patient or current.patient_id is None:
        raise HTTPException(status_code=403, detail="Patient account required")
    return current


PatientUserDep = Annotated[CurrentUser, Depends(require_patient)]


def require_clinician(current: CurrentUserDep) -> CurrentUser:
    """Clinician-scoped endpoints: the caller must be a clinician bound to a clinic."""
    if current.role is not UserRole.clinician or current.clinic_id is None:
        raise HTTPException(status_code=403, detail="Clinician account required")
    return current


ClinicianUserDep = Annotated[CurrentUser, Depends(require_clinician)]


def require_caregiver(current: CurrentUserDep) -> CurrentUser:
    """Caregiver-scoped endpoints (ADR-0047): the caller must be a caregiver user.

    A caregiver carries neither patient_id nor clinic_id (the ops account shape) and
    is NEVER a clinician — no clinical authority, read-only in Phase A."""
    if current.role is not UserRole.caregiver:
        raise HTTPException(status_code=403, detail="Caregiver account required")
    return current


CaregiverUserDep = Annotated[CurrentUser, Depends(require_caregiver)]


def require_privileged(current: CurrentUserDep) -> CurrentUser:
    """Privileged (clinician/ops) endpoints — the MFA enrollment surface (§1B C6).

    Explicitly clinician-or-ops, NOT merely "not a patient": patients can never hold
    an MFA factor, and caregivers (ADR-0047 — no clinical authority) are refused
    too, so both auth flows are structurally untouched by the whole feature."""
    if current.role is not UserRole.clinician and current.role is not UserRole.ops:
        raise HTTPException(status_code=403, detail="Clinician or ops account required")
    return current


PrivilegedUserDep = Annotated[CurrentUser, Depends(require_privileged)]


def require_ops(current: CurrentUserDep) -> CurrentUser:
    """Ops-scoped endpoints (ADR-0019): the caller must be an ops operator.

    An ops principal carries neither patient_id nor clinic_id. Revocation is enforced
    centrally in get_current_user now (a deactivated principal of ANY role is refused at
    authentication, before it reaches any gate), so the active re-check kept here is
    pure defense-in-depth — it can only ever see an active principal through the request
    path, and never produces a second, differing status for the deactivated case."""
    if current.role is not UserRole.ops or not current.active:
        raise HTTPException(status_code=403, detail="Ops account required")
    return current


OpsUserDep = Annotated[CurrentUser, Depends(require_ops)]


@lru_cache(maxsize=1)
def _process_transport() -> HttpxTransport:
    """One pooled HTTP client per process for EMR calls."""
    return HttpxTransport()


@lru_cache(maxsize=1)
def _process_secret_store() -> InMemorySecretStore:
    """Process-wide OAuth token vault for in-memory mode — and the fail-closed
    fallback for DB mode without a SECRET_STORE_KEY (ADR-0017): tokens must never
    land in the database unencrypted, so no key means they stay in this process."""
    return InMemorySecretStore()


@lru_cache(maxsize=1)
def _process_clinical_note_repo() -> InMemoryEmrClinicalNoteRepository:
    """Process-wide clinical-note store for in-memory mode — shared by EMR/visit-summary/
    export/deletion so every feature reads/writes the SAME notes (ADR-0045 P2 #27)."""
    return InMemoryEmrClinicalNoteRepository()


@lru_cache(maxsize=1)
def _process_note_signal_sink() -> InMemoryNewChartNoteSink:
    """Process-wide new-chart-note signal sink for in-memory mode. The caregiver consumer
    (ADR-0047) is out of scope; this just records emitted signals so tests can inspect them."""
    return InMemoryNewChartNoteSink()


@lru_cache(maxsize=1)
def _process_pending_auth() -> InMemoryPendingAuthStore:
    """Process-wide OAuth state->verifier store for in-memory mode: connect and
    callback are separate requests, so pending state must outlive each. DB mode uses
    the durable Postgres store instead (ADR-0017)."""
    return InMemoryPendingAuthStore()


@lru_cache(maxsize=1)
def _process_fernet() -> Fernet | None:
    """The token-vault key, parsed once per process. None = no key configured; the
    shape was already validated at settings load (app/core/config.py)."""
    if not settings.secret_store_key:
        if settings.database_url:
            _log.warning(
                "SECRET_STORE_KEY is not configured: EMR OAuth tokens stay in the "
                "per-process in-memory vault and will not survive a restart or reach "
                "other workers. Configure the key to enable the encrypted DB vault "
                "(ADR-0017); plaintext tokens are never written to the database."
            )
        return None
    return Fernet(settings.secret_store_key)


def _secret_store_for(session: AsyncSession) -> SecretStore:
    """DB mode's vault: encrypted-at-rest Postgres when the key is configured,
    otherwise the fail-closed per-process store (never plaintext in the DB)."""
    fernet = _process_fernet()
    if fernet is None:
        return _process_secret_store()
    return PostgresSecretStore(session, fernet)


def _smart_client_config() -> tuple[str, str]:
    """(fallback client_id, redirect_uri) with DB-less-dev fallbacks.

    The client-id placeholder is deliberately the service's UNCONFIGURED sentinel:
    POST /emr/connect refuses to build an authorize URL around it (422 naming the env
    var to set) instead of sending the patient to the real EMR to hit an opaque
    vendor-side invalid_client error."""
    return (
        settings.smart_client_id or UNCONFIGURED_CLIENT_ID,
        settings.smart_redirect_uri or "http://localhost:8000/emr/callback",
    )


def _smart_provider_client_ids() -> dict[str, str]:
    """Vendor-issued client ids from the registry + settings (ADR-0028).

    Keyed by provider display name — what a ConnectionRecord persists — so the service
    resolves the SAME id on both handshake hops (see EmrService.provider_client_ids).
    Unconfigured providers are simply absent and fall back to the generic client id.
    """
    ids: dict[str, str] = {}
    for provider in TOP_PROVIDERS:
        configured = client_id_for(provider)
        if configured is not None:
            ids[provider.name] = configured
    return ids


@lru_cache(maxsize=1)
def _default_emr_service() -> EmrService:
    """Process-wide EmrService for in-memory mode — the single home of the shared
    observation/audit stores so every feature reads/writes the SAME data. Per-process
    and non-durable by design; DB mode (get_emr_service) is the durable path."""
    client_id, redirect_uri = _smart_client_config()
    return EmrService(
        transport=_process_transport(),
        client_id=client_id,
        redirect_uri=redirect_uri,
        provider_client_ids=_smart_provider_client_ids(),
        secret_store=_process_secret_store(),
        clinical_notes=_process_clinical_note_repo(),
        note_signals=_process_note_signal_sink(),
        _pending=_process_pending_auth(),
    )


def get_emr_service(session: DbSessionDep = None) -> EmrService:
    if session is None:
        return _default_emr_service()
    client_id, redirect_uri = _smart_client_config()
    return EmrService(
        transport=_process_transport(),
        client_id=client_id,
        redirect_uri=redirect_uri,
        provider_client_ids=_smart_provider_client_ids(),
        secret_store=_secret_store_for(session),
        connections=PostgresEmrConnectionRepository(session),
        observations=PostgresObservationRepository(session),
        clinical_notes=PostgresEmrClinicalNoteRepository(session),
        audit=PostgresAuditEventRepository(session),
        # Durable + single-use across processes/workers (ADR-0017): the connect and
        # callback requests may land anywhere, so pending state lives in the DB.
        _pending=PostgresPendingAuthStore(session),
    )


EmrServiceDep = Annotated[EmrService, Depends(get_emr_service)]


@lru_cache(maxsize=1)
def _process_capability_repo() -> InMemoryCapabilityRepository:
    """Process-wide capability registry store for in-memory mode — shared by the
    clinic and capability services so the `share_with_clinic` consent gate (ADR-0020)
    reads exactly the rows the toggle endpoints wrote."""
    return InMemoryCapabilityRepository()


@lru_cache(maxsize=1)
def _process_patient_capability_repo() -> InMemoryPatientCapabilityRepository:
    """Process-wide per-patient toggle store for in-memory mode — shared like the
    registry above so clinician reads and patient toggle writes never drift."""
    return InMemoryPatientCapabilityRepository()


@lru_cache(maxsize=1)
def _default_clinic_service() -> ClinicService:
    """Process-wide ClinicService for in-memory mode. Users, observations, and audit
    are the SAME stores auth and EMR use (deps singletons), so a clinician reads
    exactly the data the patient's own endpoints wrote. The capability stores are the
    SAME ones the capability service uses, so the share_with_clinic read gate tracks
    the patient's live consent (ADR-0020)."""
    emr = _default_emr_service()
    return ClinicService(
        users=_default_auth_service().users,
        observations=emr.observations,
        clinical_notes=emr.clinical_notes,
        audit=emr.audit,
        capabilities=_process_capability_repo(),
        patient_capabilities=_process_patient_capability_repo(),
    )


def get_clinic_service(session: DbSessionDep = None) -> ClinicService:
    if session is None:
        return _default_clinic_service()
    return ClinicService(
        clinics=PostgresClinicRepository(session),
        connections=PostgresClinicConnectionRepository(session),
        users=PostgresUserRepository(session),
        observations=PostgresObservationRepository(session),
        clinical_notes=PostgresEmrClinicalNoteRepository(session),
        audit=PostgresAuditEventRepository(session),
        # Same session-bound rows the capability service writes — the share_with_clinic
        # read gate and the toggle writes stay consistent within the request (ADR-0020).
        capabilities=PostgresCapabilityRepository(session),
        patient_capabilities=PostgresPatientCapabilityRepository(session),
    )


ClinicServiceDep = Annotated[ClinicService, Depends(get_clinic_service)]


@lru_cache(maxsize=1)
def _process_caregiver_invite_repo() -> InMemoryCaregiverInviteRepository:
    """Process-wide caregiver-invite store for in-memory mode (ADR-0047) — shared by
    the caregiver and account-deletion services so a deletion purges exactly the
    invites the patient's own endpoints created."""
    return InMemoryCaregiverInviteRepository()


@lru_cache(maxsize=1)
def _process_caregiver_link_repo() -> InMemoryCaregiverLinkRepository:
    """Process-wide caregiver-link store for in-memory mode (ADR-0047) — shared by
    the caregiver, account-deletion, and export services so revocation, deletion,
    and the export all see the SAME links."""
    return InMemoryCaregiverLinkRepository()


@lru_cache(maxsize=1)
def _default_caregiver_service() -> CaregiverService:
    """Process-wide CaregiverService for in-memory mode (ADR-0047). Users,
    observations, clinical notes, and audit are the SAME stores auth and EMR use
    (deps singletons), so a caregiver reads exactly the data the patient's own
    endpoints wrote and every claim/lifecycle event lands in the one shared trail."""
    emr = _default_emr_service()
    return CaregiverService(
        invites=_process_caregiver_invite_repo(),
        links=_process_caregiver_link_repo(),
        users=_default_auth_service().users,
        observations=emr.observations,
        clinical_notes=emr.clinical_notes,
        audit=emr.audit,
    )


def get_caregiver_service(session: DbSessionDep = None) -> CaregiverService:
    if session is None:
        return _default_caregiver_service()
    return CaregiverService(
        invites=PostgresCaregiverInviteRepository(session),
        links=PostgresCaregiverLinkRepository(session),
        users=PostgresUserRepository(session),
        observations=PostgresObservationRepository(session),
        clinical_notes=PostgresEmrClinicalNoteRepository(session),
        audit=PostgresAuditEventRepository(session),
    )


CaregiverServiceDep = Annotated[CaregiverService, Depends(get_caregiver_service)]


@lru_cache(maxsize=1)
def _process_caregiver_alert_repo() -> InMemoryCaregiverAlertRepository:
    """Process-wide caregiver-alert store for in-memory mode (ADR-0047 B1) — shared by
    the alert, account-deletion, and export flows so the feed, the erasure sweeps, and
    the export all see the SAME alerts. It resolves caregiver-scoped deletes through the
    SAME shared link store the caregiver service uses."""
    return InMemoryCaregiverAlertRepository(links=_process_caregiver_link_repo())


@lru_cache(maxsize=1)
def _process_caregiver_alert_pref_repo() -> InMemoryCaregiverAlertPreferenceRepository:
    """Process-wide caregiver-alert preference store for in-memory mode (ADR-0047 B1) —
    shared so a patient's toggle write gates the caregiver's very next feed read."""
    return InMemoryCaregiverAlertPreferenceRepository()


@lru_cache(maxsize=1)
def _process_caregiver_push_token_repo() -> InMemoryCaregiverPushTokenRepository:
    """Process-wide caregiver push-token store for in-memory mode (ADR-0047 B2) — shared
    by the register/deregister endpoints, the account-deletion sweep, and the post-commit
    FCM fan-out, so a token registered on one request is the one the fan-out delivers to
    (and the deletion purges)."""
    return InMemoryCaregiverPushTokenRepository()


def get_caregiver_push_token_repo(session: DbSessionDep = None) -> CaregiverPushTokenRepository:
    if session is None:
        return _process_caregiver_push_token_repo()
    return PostgresCaregiverPushTokenRepository(session)


CaregiverPushTokenRepoDep = Annotated[
    CaregiverPushTokenRepository, Depends(get_caregiver_push_token_repo)
]


@lru_cache(maxsize=1)
def _process_fcm_transport() -> HttpxPushTransport:
    """One pooled HTTP client per process for FCM calls (mirrors _process_transport)."""
    return HttpxPushTransport()


def _load_fcm_credentials() -> dict[str, Any] | None:
    """The Firebase service-account JSON, from settings.fcm_credentials_json (the raw
    JSON, injected as a secret) or the GOOGLE_APPLICATION_CREDENTIALS file (a path).
    NEVER a committed key. Fail SAFE: any parse/read error returns None (PHI-free warning,
    no crash), so deps selects the no-op path rather than booting a broken sender."""
    raw = settings.fcm_credentials_json
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            _log.warning(
                "FCM_CREDENTIALS_JSON is set but is not valid JSON; caregiver push stays "
                "a no-op (fail-safe)."
            )
            return None
        return parsed if isinstance(parsed, dict) else None
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if path:
        try:
            with open(path, encoding="utf-8") as handle:
                parsed = json.load(handle)
        except (OSError, json.JSONDecodeError):
            _log.warning(
                "GOOGLE_APPLICATION_CREDENTIALS is set but could not be read as JSON; "
                "caregiver push stays a no-op (fail-safe)."
            )
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


@lru_cache(maxsize=1)
def _process_fcm_sender() -> FcmPushSender | None:
    """The REAL FCM sender, built ONCE per process (its cached OAuth token is reused
    across sends), or None when push is disabled / no credential is present / the
    credential is malformed — every one of those cases fails SAFE to the no-op path
    (ADR-0047 B2). Cached, so the credential is parsed and the JWT signer built once."""
    if not settings.caregiver_push_enabled:
        return None
    credentials = _load_fcm_credentials()
    if credentials is None:
        _log.warning(
            "CAREGIVER_PUSH_ENABLED is true but no FCM service-account credential is "
            "configured; caregiver push stays a no-op (fail-safe)."
        )
        return None
    try:
        return FcmPushSender(transport=_process_fcm_transport(), service_account_info=credentials)
    except FcmCredentialsError:
        _log.warning(
            "The configured FCM service-account credential could not be loaded; "
            "caregiver push stays a no-op (fail-safe)."
        )
        return None


@dataclass
class CaregiverPushDispatcher:
    """Schedules the post-commit caregiver-push fan-out (ADR-0047 B2).

    The route calls ``schedule`` after building the feed response; the fan-out runs as a
    Starlette BackgroundTask AFTER the response is sent — i.e. after the request
    transaction commits — and opens its OWN short-lived session (the request's is closed)
    to read tokens and prune dead ones. A None ``sender`` (push disabled / no credential)
    makes ``schedule`` a no-op, so the whole feature fails safe."""

    sender: FcmPushSender | None
    sessionmaker: async_sessionmaker[AsyncSession] | None

    def schedule(self, background: BackgroundTasks, messages: list[PushMessage]) -> None:
        if self.sender is None or not messages:
            return
        background.add_task(self._run, list(messages))

    async def _run(self, messages: list[PushMessage]) -> None:
        assert self.sender is not None  # guarded by schedule
        if self.sessionmaker is not None:
            async with self.sessionmaker() as session, session.begin():
                tokens: CaregiverPushTokenRepository = PostgresCaregiverPushTokenRepository(session)
                await fan_out_caregiver_push(messages=messages, tokens=tokens, sender=self.sender)
        else:
            await fan_out_caregiver_push(
                messages=messages,
                tokens=_process_caregiver_push_token_repo(),
                sender=self.sender,
            )


def get_caregiver_push_dispatcher(request: Request) -> CaregiverPushDispatcher:
    maker: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "db_sessionmaker", None
    )
    return CaregiverPushDispatcher(sender=_process_fcm_sender(), sessionmaker=maker)


CaregiverPushDispatcherDep = Annotated[
    CaregiverPushDispatcher, Depends(get_caregiver_push_dispatcher)
]


@lru_cache(maxsize=1)
def _default_caregiver_alert_service() -> CaregiverAlertService:
    """Process-wide CaregiverAlertService for in-memory mode (ADR-0047 B1). The caregiver
    service (the SINGLE consent predicate), observations, clinical notes, and audit are
    the SAME shared singletons every other feature uses, so the alert engine reads
    exactly the data the patient's own endpoints wrote and every alert event lands in
    the one shared trail. New-alert pushes accrue on the service and are fanned out
    post-commit by the route (ADR-0047 B2)."""
    emr = _default_emr_service()
    return CaregiverAlertService(
        caregivers=_default_caregiver_service(),
        alerts=_process_caregiver_alert_repo(),
        preferences=_process_caregiver_alert_pref_repo(),
        observations=emr.observations,
        clinical_notes=emr.clinical_notes,
        audit=emr.audit,
    )


def get_caregiver_alert_service(session: DbSessionDep = None) -> CaregiverAlertService:
    if session is None:
        return _default_caregiver_alert_service()
    return CaregiverAlertService(
        caregivers=get_caregiver_service(session),
        alerts=PostgresCaregiverAlertRepository(session),
        preferences=PostgresCaregiverAlertPreferenceRepository(session),
        observations=PostgresObservationRepository(session),
        clinical_notes=PostgresEmrClinicalNoteRepository(session),
        audit=PostgresAuditEventRepository(session),
    )


CaregiverAlertServiceDep = Annotated[CaregiverAlertService, Depends(get_caregiver_alert_service)]


@lru_cache(maxsize=1)
def _default_capability_service() -> CapabilityService:
    """Process-wide CapabilityService for in-memory mode. Connections and audit are
    the SAME stores the clinic service uses (deps singletons), so toggle authority
    tracks exactly the consent state the connection endpoints wrote; the capability
    stores are likewise shared so the clinic service's share_with_clinic gate sees
    every toggle write (ADR-0020)."""
    clinic = _default_clinic_service()
    return CapabilityService(
        capabilities=_process_capability_repo(),
        patient_capabilities=_process_patient_capability_repo(),
        connections=clinic.connections,
        audit=clinic.audit,
    )


def get_capability_service(session: DbSessionDep = None) -> CapabilityService:
    if session is None:
        return _default_capability_service()
    return CapabilityService(
        capabilities=PostgresCapabilityRepository(session),
        patient_capabilities=PostgresPatientCapabilityRepository(session),
        connections=PostgresClinicConnectionRepository(session),
        audit=PostgresAuditEventRepository(session),
    )


CapabilityServiceDep = Annotated[CapabilityService, Depends(get_capability_service)]


@lru_cache(maxsize=1)
def _default_account_deletion_service() -> AccountDeletionService:
    """Process-wide AccountDeletionService for in-memory mode (ADR-0027). Every store
    is the SAME singleton the auth/EMR/clinic/capability services use, so the
    deletion removes exactly the data those features wrote — including the vaulted
    EMR tokens, purged through the same in-memory SecretStore revoke uses."""
    emr = _default_emr_service()
    return AccountDeletionService(
        users=_default_auth_service().users,
        emr_connections=emr.connections,
        pending_auth=emr._pending,
        secret_store=emr.secret_store,
        clinic_connections=_default_clinic_service().connections,
        patient_capabilities=_process_patient_capability_repo(),
        observations=emr.observations,
        clinical_notes=emr.clinical_notes,
        caregiver_invites=_process_caregiver_invite_repo(),
        caregiver_links=_process_caregiver_link_repo(),
        caregiver_alerts=_process_caregiver_alert_repo(),
        caregiver_alert_preferences=_process_caregiver_alert_pref_repo(),
        caregiver_push_tokens=_process_caregiver_push_token_repo(),
        audit=emr.audit,
    )


def get_account_deletion_service(session: DbSessionDep = None) -> AccountDeletionService:
    if session is None:
        return _default_account_deletion_service()
    return AccountDeletionService(
        users=PostgresUserRepository(session),
        emr_connections=PostgresEmrConnectionRepository(session),
        pending_auth=PostgresPendingAuthStore(session),
        # The same fail-closed vault selection every EMR request gets (ADR-0017):
        # encrypted Postgres vault with a key, the per-process store without one —
        # so deletion purges tokens from wherever they actually live.
        secret_store=_secret_store_for(session),
        clinic_connections=PostgresClinicConnectionRepository(session),
        patient_capabilities=PostgresPatientCapabilityRepository(session),
        observations=PostgresObservationRepository(session),
        clinical_notes=PostgresEmrClinicalNoteRepository(session),
        caregiver_invites=PostgresCaregiverInviteRepository(session),
        caregiver_links=PostgresCaregiverLinkRepository(session),
        caregiver_alerts=PostgresCaregiverAlertRepository(session),
        caregiver_alert_preferences=PostgresCaregiverAlertPreferenceRepository(session),
        caregiver_push_tokens=PostgresCaregiverPushTokenRepository(session),
        audit=PostgresAuditEventRepository(session),
    )


AccountDeletionDep = Annotated[AccountDeletionService, Depends(get_account_deletion_service)]


@lru_cache(maxsize=1)
def _process_mfa_factor_repo() -> InMemoryMfaFactorRepository:
    """Process-wide MFA factor store for in-memory mode (§1B C6) — one store shared
    by the enrollment endpoints and the login step-up, so a factor confirmed on one
    request gates the very next login."""
    return InMemoryMfaFactorRepository()


@lru_cache(maxsize=1)
def _default_mfa_service() -> MfaService:
    """Process-wide MfaService for in-memory mode (§1B C6). The JWT secret is the
    SAME one the auth service signs with (an mfa_pending token minted at login must
    verify here), and the vault/audit stores are the shared EMR singletons — the
    TOTP secret lives in exactly the vault EMR tokens use, never anywhere else."""
    emr = _default_emr_service()
    return MfaService(
        secret=_default_auth_service().secret,
        users=_default_auth_service().users,
        factors=_process_mfa_factor_repo(),
        secret_store=emr.secret_store,
        audit=emr.audit,
    )


def get_mfa_service(session: DbSessionDep = None) -> MfaService:
    if session is None:
        return _default_mfa_service()
    return MfaService(
        secret=_process_jwt_secret(),
        users=PostgresUserRepository(session),
        factors=PostgresMfaFactorRepository(session),
        # The same fail-closed vault selection every EMR request gets (ADR-0017):
        # encrypted Postgres vault with a key, the per-process store without one —
        # the TOTP secret is never written to the database unencrypted.
        secret_store=_secret_store_for(session),
        audit=PostgresAuditEventRepository(session),
    )


MfaDep = Annotated[MfaService, Depends(get_mfa_service)]


@lru_cache(maxsize=1)
def _default_patient_data_export_service() -> PatientDataExportService:
    """Process-wide PatientDataExportService for in-memory mode (ADR-0031). Every store
    and service is the SAME singleton the auth/EMR/clinic/capability features use, so
    the export reflects exactly the data those features wrote — read-only, plus the one
    audit event, through the shared audit store."""
    emr = _default_emr_service()
    return PatientDataExportService(
        users=_default_auth_service().users,
        observations=emr.observations,
        emr_connections=emr.connections,
        clinical_notes=emr.clinical_notes,
        caregiver_links=_process_caregiver_link_repo(),
        caregiver_alerts=_process_caregiver_alert_repo(),
        caregiver_alert_preferences=_process_caregiver_alert_pref_repo(),
        clinic=_default_clinic_service(),
        capabilities=_default_capability_service(),
        audit=emr.audit,
    )


def get_patient_data_export_service(session: DbSessionDep = None) -> PatientDataExportService:
    if session is None:
        return _default_patient_data_export_service()
    return PatientDataExportService(
        users=PostgresUserRepository(session),
        observations=PostgresObservationRepository(session),
        emr_connections=PostgresEmrConnectionRepository(session),
        clinical_notes=PostgresEmrClinicalNoteRepository(session),
        caregiver_links=PostgresCaregiverLinkRepository(session),
        caregiver_alerts=PostgresCaregiverAlertRepository(session),
        caregiver_alert_preferences=PostgresCaregiverAlertPreferenceRepository(session),
        # Compose the clinic/capability services on the SAME session so their reads
        # (clinic names, effective toggle states) join the request transaction.
        clinic=get_clinic_service(session),
        capabilities=get_capability_service(session),
        audit=PostgresAuditEventRepository(session),
    )


PatientDataExportDep = Annotated[PatientDataExportService, Depends(get_patient_data_export_service)]


def require_capability(key: str) -> Callable[[CurrentUser, CapabilityService], Awaitable[None]]:
    """The enforcement seam (ADR-0013): a dependency that refuses the request (409)
    when the named capability is effectively off for the authenticated patient.

    Feature endpoints adopt it incrementally:
    `dependencies=[Depends(require_capability("ingest_adl"))]`. Absence of a toggle
    row means the registry default, so unwired and never-toggled features behave
    exactly as before."""

    async def _gate(current: PatientUserDep, service: CapabilityServiceDep) -> None:
        assert current.patient_id is not None  # guaranteed by require_patient
        if not await service.is_active(current.patient_id, key, now=datetime.now(UTC)):
            raise HTTPException(status_code=409, detail="This feature is turned off")

    return _gate


@lru_cache(maxsize=1)
def _default_narrator() -> Narrator | None:
    """The AI narrative layer activates ONLY with a key AND the operator's explicit
    BAA attestation (ADR-0011) — a key alone keeps it off, fail-safe. The BAA
    attestation is bound to the provider actually called, so both gates are checked
    before ANY provider is constructed.

    Provider is chosen by settings.ai_provider (ADR-0040): unset/"anthropic" →
    Anthropic; "azure_openai"/"azure" → Azure OpenAI (HIPAA-eligible under Microsoft's
    BAA). A misconfigured or unknown provider stays OFF — fail-safe."""
    if not (settings.ai_api_key and settings.ai_baa_confirmed):
        return None
    provider = (settings.ai_provider or "anthropic").lower()
    if provider in ("", "anthropic"):
        return AnthropicNarrator(api_key=settings.ai_api_key, model=settings.ai_model)
    if provider in ("azure", "azure_openai", "azureopenai"):
        # Azure needs an endpoint; without it the provider is misconfigured — stay off.
        if not settings.ai_azure_endpoint:
            return None
        return AzureOpenAINarrator(
            api_key=settings.ai_api_key,
            endpoint=settings.ai_azure_endpoint,
            deployment=settings.ai_azure_deployment or settings.ai_model,
            api_version=settings.ai_azure_api_version,
        )
    return None  # unknown provider: stay off, fail-safe


def get_narrator() -> Narrator | None:
    return _default_narrator()


NarratorDep = Annotated[Narrator | None, Depends(get_narrator)]


def get_nutrition_source() -> NutritionSource:
    """The food-estimate seam (ADR-0042). Phase 1 always returns NullNutritionSource — no
    automated estimate, so the flow falls back to manual ranged entry. Phase 2/3 select a
    DB-backed source (Open Food Facts / USDA) or the BAA-gated photo source here, mirroring
    _default_narrator's gate; the route and frontend need no change."""
    return NullNutritionSource()


NutritionSourceDep = Annotated[NutritionSource, Depends(get_nutrition_source)]


@lru_cache(maxsize=1)
def _default_error_reporter() -> HttpErrorReporter | None:
    """The error-reporting seam activates ONLY when a self-hosted collector URL is
    configured (ADR-0021) — unset means OFF, fail-safe, exactly like the narrator seam is
    off without a key + BAA. One pooled reporter per process (holds an httpx client)."""
    if settings.error_reporting_dsn:
        return HttpErrorReporter(
            settings.error_reporting_dsn, timeout=settings.error_reporting_timeout_seconds
        )
    return None


def get_error_reporter() -> ErrorReporter | None:
    """Reporter accessor for the error-reporting middleware (mirrors get_narrator).

    Not a request dependency: the middleware resolves it per request via this function so
    a test can monkeypatch the module-level factory to inject a stub or force OFF."""
    return _default_error_reporter()
