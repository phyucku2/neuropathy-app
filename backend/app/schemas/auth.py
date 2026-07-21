"""API contracts for authentication (ADR-0010). Hashes never leave the service layer."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field

from app.schemas.base import ApiModel


class RegisterIn(ApiModel):
    email: EmailStr
    # NIST 800-63B: length over composition rules.
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=200)


class LoginIn(ApiModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(ApiModel):
    refresh_token: str


class MfaPendingOut(BaseModel):
    """POST /auth/login's step-up answer (§1B C6): password verified, 6-digit code
    still owed. The token is a distinct short-lived ``mfa_pending`` JWT kind — the
    kind check refuses it as an access or refresh token everywhere."""

    mfa_pending_token: str
    token_type: str = "mfa_pending"


class MfaVerifyIn(ApiModel):
    """The login step-up exchange: the pending token rides in the BODY (it is not an
    access token and must never be presented as a bearer) plus the 6-digit code."""

    mfa_pending_token: str
    code: str


class MfaCodeIn(ApiModel):
    """A 6-digit authenticator code (enrollment confirmation)."""

    code: str


class MfaEnrollOut(BaseModel):
    """The one-time enrollment payload (§1B C6): otpauth:// URI + base32 secret,
    returned ONCE — the server keeps only the vault-encrypted copy, so there is no
    re-read endpoint."""

    otpauth_uri: str
    secret: str


class MfaStatusOut(BaseModel):
    """Whether the signed-in account holds a CONFIRMED authenticator factor."""

    enrolled: bool


class DeleteAccountIn(ApiModel):
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
