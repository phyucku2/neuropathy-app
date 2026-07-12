"""Authentication endpoints (ADR-0010): register, login, refresh, me."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import AuthDep, CurrentUserDep
from app.core.security import AuthError
from app.schemas.auth import (
    AccessTokenOut,
    LoginIn,
    MeOut,
    RefreshIn,
    RegisterIn,
    TokenOut,
)
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


@router.get("/me", response_model=MeOut)
async def me(current: CurrentUserDep) -> MeOut:
    return MeOut(
        user_id=current.user_id,
        email=current.email,
        display_name=current.display_name,
        role=current.role.value,
        patient_id=current.patient_id,
    )
