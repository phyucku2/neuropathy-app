"""Shared API dependencies — the authenticated current user (ADR-0010) and the
storage-mode-aware service providers.

Two storage modes, selected per request by `get_db_session` (app/db/session.py):

- **Postgres mode** (DATABASE_URL configured — the dependency yields a session):
  services are constructed per request on Postgres repositories bound to the
  request-scoped transaction. State that must outlive one request — the JWT signing
  secret, the OAuth state->PKCE-verifier map, and the token secret store — is hoisted
  to the process-level singletons below and shared by every request-scoped instance.
  Documented limitation: pending auth states and OAuth tokens are still per-process;
  a durable secret-manager adapter and a DB-backed pending store are follow-ups.
- **In-memory mode** (no DATABASE_URL — the dependency yields None): the lru_cache
  service singletons serve every request, exactly as before. Unit tests and DB-less
  development are unchanged, and tests keep overriding get_auth_service /
  get_emr_service directly.
"""

from __future__ import annotations

import secrets as pysecrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.narrative import AnthropicNarrator, Narrator
from app.core.config import settings
from app.core.security import AuthError, TokenKind, decode_token
from app.db.session import get_db_session
from app.emr.service import EmrService, InMemorySecretStore, PendingAuthStore
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
    PostgresUserRepository,
)
from app.services.auth import AuthService
from app.services.capability import CapabilityService
from app.services.clinic import ClinicService

_bearer = HTTPBearer(auto_error=False)

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
    """Process-wide OAuth token vault shared by every request-scoped EmrService.

    Per-request stores would lose tokens between requests. Still per-process (a
    documented limitation) — the durable secret-manager adapter is a follow-up.
    """
    return InMemorySecretStore()


@lru_cache(maxsize=1)
def _process_pending_auth() -> PendingAuthStore:
    """Process-wide OAuth state->verifier map: connect and callback are separate
    requests, so pending state must outlive each. Still per-process (a documented
    limitation) — a DB-backed pending store is a follow-up."""
    return {}


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
        secret_store=_process_secret_store(),
        connections=PostgresEmrConnectionRepository(session),
        observations=PostgresObservationRepository(session),
        audit=PostgresAuditEventRepository(session),
        _pending=_process_pending_auth(),
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
