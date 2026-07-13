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

import logging
import secrets as pysecrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.narrative import AnthropicNarrator, Narrator
from app.core.config import settings
from app.core.security import AuthError, TokenKind, decode_token
from app.db.session import get_db_session
from app.emr.service import (
    EmrService,
    InMemoryPendingAuthStore,
    InMemorySecretStore,
    SecretStore,
)
from app.emr.transport import HttpxTransport
from app.models.user import UserRole
from app.repositories.postgres import (
    PostgresAuditEventRepository,
    PostgresCapabilityRepository,
    PostgresClinicConnectionRepository,
    PostgresClinicRepository,
    PostgresEmrConnectionRepository,
    PostgresObservationRepository,
    PostgresPatientCapabilityRepository,
    PostgresPendingAuthStore,
    PostgresSecretStore,
    PostgresUserRepository,
)
from app.services.auth import AuthService
from app.services.capability import CapabilityService
from app.services.clinic import ClinicService

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
    if settings.jwt_secret:
        return AuthService(secret=settings.jwt_secret)
    return AuthService()  # ephemeral dev secret (ADR-0010)


def get_auth_service(session: DbSessionDep = None) -> AuthService:
    if session is None:
        return _default_auth_service()
    return AuthService(secret=_process_jwt_secret(), users=PostgresUserRepository(session))


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
    return CurrentUser(
        user_id=user.id,
        role=user.role,
        patient_id=user.patient_id,
        email=user.email,
        display_name=user.display_name,
        clinic_id=user.clinic_id,
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
    """(client_id, redirect_uri) with DB-less-dev fallbacks."""
    return (
        settings.smart_client_id or "unconfigured-client",
        settings.smart_redirect_uri or "http://localhost:8000/emr/callback",
    )


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
        secret_store=_process_secret_store(),
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
        secret_store=_secret_store_for(session),
        connections=PostgresEmrConnectionRepository(session),
        observations=PostgresObservationRepository(session),
        audit=PostgresAuditEventRepository(session),
        # Durable + single-use across processes/workers (ADR-0017): the connect and
        # callback requests may land anywhere, so pending state lives in the DB.
        _pending=PostgresPendingAuthStore(session),
    )


EmrServiceDep = Annotated[EmrService, Depends(get_emr_service)]


@lru_cache(maxsize=1)
def _default_clinic_service() -> ClinicService:
    """Process-wide ClinicService for in-memory mode. Users, observations, and audit
    are the SAME stores auth and EMR use (deps singletons), so a clinician reads
    exactly the data the patient's own endpoints wrote."""
    emr = _default_emr_service()
    return ClinicService(
        users=_default_auth_service().users,
        observations=emr.observations,
        audit=emr.audit,
    )


def get_clinic_service(session: DbSessionDep = None) -> ClinicService:
    if session is None:
        return _default_clinic_service()
    return ClinicService(
        clinics=PostgresClinicRepository(session),
        connections=PostgresClinicConnectionRepository(session),
        users=PostgresUserRepository(session),
        observations=PostgresObservationRepository(session),
        audit=PostgresAuditEventRepository(session),
    )


ClinicServiceDep = Annotated[ClinicService, Depends(get_clinic_service)]


@lru_cache(maxsize=1)
def _default_capability_service() -> CapabilityService:
    """Process-wide CapabilityService for in-memory mode. Connections and audit are
    the SAME stores the clinic service uses (deps singletons), so toggle authority
    tracks exactly the consent state the connection endpoints wrote."""
    clinic = _default_clinic_service()
    return CapabilityService(connections=clinic.connections, audit=clinic.audit)


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
def _default_narrator() -> AnthropicNarrator | None:
    """The AI narrative layer activates ONLY with a key AND the operator's explicit
    BAA attestation (ADR-0011) — a key alone keeps it off, fail-safe."""
    provider_ok = settings.ai_provider in (None, "", "anthropic")
    if settings.ai_api_key and settings.ai_baa_confirmed and provider_ok:
        return AnthropicNarrator(api_key=settings.ai_api_key, model=settings.ai_model)
    # Any other configured provider: stay off — the BAA attestation is bound to the
    # endpoint actually called, and we only ship an Anthropic narrator (review finding).
    return None


def get_narrator() -> Narrator | None:
    return _default_narrator()


NarratorDep = Annotated[Narrator | None, Depends(get_narrator)]
