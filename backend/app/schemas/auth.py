"""API contracts for authentication (ADR-0010). Hashes never leave the service layer."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    # NIST 800-63B: length over composition rules.
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


class DeleteAccountIn(BaseModel):
    """DELETE /auth/me requires fresh password re-authentication (ADR-0027): a bearer
    token alone — which can be stolen — must never be able to destroy an account."""

    password: str


class AccessTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    role: str
    patient_id: uuid.UUID | None
