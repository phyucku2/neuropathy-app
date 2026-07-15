"""Authentication endpoints (ADR-0010): register, login, refresh, me — and the
patient account & data deletion flow (ADR-0027): DELETE /auth/me."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse

from app.api.deps import AccountDeletionDep, AuthDep, CurrentUserDep, PatientUserDep
from app.core.security import AuthError
from app.schemas.auth import (
    AccessTokenOut,
    DeleteAccountIn,
    LoginIn,
    MeOut,
    RefreshIn,
    RegisterIn,
    TokenOut,
)
from app.services.account_deletion import AccountDeletionError
from app.services.auth import AuthApiError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=201)
async def register(body: RegisterIn, auth: AuthDep) -> TokenOut:
    try:
        await auth.register_patient(
            email=body.email, password=body.password, display_name=body.display_name
        )
        _, tokens = await auth.login(email=body.email, password=body.password)
    except AuthApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    return TokenOut(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, auth: AuthDep) -> TokenOut:
    try:
        _, tokens = await auth.login(email=body.email, password=body.password)
    except AuthApiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.reason,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return TokenOut(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/refresh", response_model=AccessTokenOut)
async def refresh(body: RefreshIn, auth: AuthDep) -> AccessTokenOut:
    try:
        access_token = await auth.refresh(refresh_token=body.refresh_token)
    except (AuthApiError, AuthError) as exc:
        reason = exc.reason if isinstance(exc, (AuthApiError, AuthError)) else "Invalid token"
        raise HTTPException(
            status_code=401, detail=reason, headers={"WWW-Authenticate": "Bearer"}
        ) from exc
    return AccessTokenOut(access_token=access_token)


@router.delete("/me", status_code=204)
async def delete_me(
    body: DeleteAccountIn, current: PatientUserDep, service: AccountDeletionDep
) -> Response:
    """Delete the authenticated PATIENT account and all its data (ADR-0027).

    Patient role only — require_patient answers 403 for clinician/ops principals.
    The body's password is fresh re-authentication (a stolen bearer token alone must
    not destroy an account); a mismatch is 403 and deletes nothing, and failed
    attempts are throttled — over the per-actor budget the answer is 429 before the
    password is even verified. Deliberately NO require_capability gate: like
    revocation (ADR-0013), deletion must never be blockable by a toggle or kill
    switch. Transactional: one PHI-free audit event + every delete commit together,
    or the whole request rolls back.

    The wrong-password refusal is RETURNED by the service and rendered here rather
    than raised: its bounded 'account_delete_denied' audit event must commit with
    the request transaction, and a raised HTTPException would roll it back
    (docs/lessons.md "return don't raise") — the throttle would then never trip.
    """
    try:
        denied = await service.delete_patient_account(
            user_id=current.user_id, password=body.password
        )
    except AccountDeletionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    if denied is not None:
        return JSONResponse(status_code=denied.status_code, content={"detail": denied.reason})
    return Response(status_code=204)


@router.get("/me", response_model=MeOut)
async def me(current: CurrentUserDep) -> MeOut:
    return MeOut(
        user_id=current.user_id,
        email=current.email,
        display_name=current.display_name,
        role=current.role.value,
        patient_id=current.patient_id,
    )
