"""Shared API dependencies — the authenticated current user (ADR-0010)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.security import AuthError, TokenKind, decode_token
from app.emr.service import EmrService
from app.emr.transport import HttpxTransport
from app.models.user import UserRole
from app.services.auth import AuthService

_bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _default_auth_service() -> AuthService:
    if settings.jwt_secret:
        return AuthService(secret=settings.jwt_secret)
    return AuthService()  # ephemeral dev secret (ADR-0010)


def get_auth_service() -> AuthService:
    return _default_auth_service()


AuthDep = Annotated[AuthService, Depends(get_auth_service)]


@dataclass(frozen=True)
class CurrentUser:
    user_id: uuid.UUID
    role: UserRole
    patient_id: uuid.UUID | None
    email: str
    display_name: str


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
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_patient(current: CurrentUserDep) -> CurrentUser:
    """Patient-scoped endpoints: the caller must be a patient user with a record."""
    if current.role is not UserRole.patient or current.patient_id is None:
        raise HTTPException(status_code=403, detail="Patient account required")
    return current


PatientUserDep = Annotated[CurrentUser, Depends(require_patient)]


@lru_cache(maxsize=1)
def _default_emr_service() -> EmrService:
    """Process-wide EmrService — the single home of the shared in-memory stores.

    Living in deps.py (not a route module) so every feature reads/writes the SAME
    observation/audit stores. Replaced by request-scoped, DB-backed repositories when
    DATABASE_URL wiring lands; until then state is per-process and non-durable.
    """
    return EmrService(
        transport=HttpxTransport(),
        client_id=settings.smart_client_id or "unconfigured-client",
        redirect_uri=settings.smart_redirect_uri or "http://localhost:8000/emr/callback",
    )


def get_emr_service() -> EmrService:
    return _default_emr_service()


EmrServiceDep = Annotated[EmrService, Depends(get_emr_service)]
