"""Authentication endpoints (ADR-0010): register, login, refresh, me — the patient
account & data deletion flow (ADR-0027): DELETE /auth/me — and the MFA (TOTP) surface
for privileged accounts (§1B C6): /auth/mfa*.

Login, refresh, and the MFA step-up are throttled (§1B C5): audited refusals come
back from the services as RETURNED denial values and are rendered here as
JSONResponses, never raised — a raised HTTPException would roll their audit events
back with the request transaction (docs/lessons.md "return don't raise").
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse

from app.api.deps import (
    AccountDeletionDep,
    AuthDep,
    CurrentUserDep,
    MfaDep,
    PatientUserDep,
    PrivilegedUserDep,
)
from app.core.security import AuthError
from app.schemas.auth import (
    AccessTokenOut,
    DeleteAccountIn,
    LoginIn,
    MeOut,
    MfaCodeIn,
    MfaEnrollOut,
    MfaPendingOut,
    MfaStatusOut,
    MfaVerifyIn,
    RefreshIn,
    RegisterIn,
    TokenOut,
)
from app.services.account_deletion import AccountDeletionError
from app.services.auth import AuthApiError, LoginDenied
from app.services.mfa import MfaApiError, MfaEnrollmentRequired, MfaStepUpRequired

router = APIRouter(prefix="/auth", tags=["auth"])


def _denied(denial: LoginDenied) -> JSONResponse:
    """Render an audited auth refusal (401/429) — returned so its audit row commits."""
    headers = {"WWW-Authenticate": "Bearer"} if denial.status_code == 401 else None
    return JSONResponse(
        status_code=denial.status_code, content={"detail": denial.reason}, headers=headers
    )


@router.post("/register", response_model=TokenOut, status_code=201)
async def register(body: RegisterIn, auth: AuthDep) -> TokenOut | JSONResponse:
    try:
        await auth.register_patient(
            email=body.email, password=body.password, display_name=body.display_name
        )
    except AuthApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    outcome = await auth.login(email=body.email, password=body.password)
    if isinstance(outcome, LoginDenied):
        # Only the throttle can fire here (the credentials were just created): prior
        # failed guesses against this email spent its sentinel budget (§1B C5).
        return _denied(outcome)
    _, tokens = outcome
    return TokenOut(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/login", response_model=TokenOut | MfaPendingOut)
async def login(body: LoginIn, auth: AuthDep, mfa: MfaDep) -> TokenOut | MfaPendingOut | Response:
    """Password login, throttled and audited (§1B C5), with the MFA step-up (§1B C6).

    Patients always get full tokens. A clinician/ops account with a CONFIRMED
    authenticator factor gets ONLY a short-lived mfa_pending token — the real tokens
    are minted by POST /auth/mfa/verify. With mfa_required_for_privileged on, an
    UNENROLLED privileged account is refused with an enrollment-required 403.
    """
    outcome = await auth.login(email=body.email, password=body.password)
    if isinstance(outcome, LoginDenied):
        return _denied(outcome)
    user, tokens = outcome
    step_up = await mfa.login_step_up(user)
    if isinstance(step_up, MfaStepUpRequired):
        return MfaPendingOut(mfa_pending_token=step_up.mfa_pending_token)
    if isinstance(step_up, MfaEnrollmentRequired):
        # Nothing audited on this path — safe to render directly. The password DID
        # verify, so naming the enrollment requirement discloses nothing to anyone
        # not already holding the credential.
        return JSONResponse(status_code=403, content={"detail": step_up.reason})
    return TokenOut(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/refresh", response_model=AccessTokenOut)
async def refresh(body: RefreshIn, auth: AuthDep) -> AccessTokenOut | JSONResponse:
    try:
        result = await auth.refresh(refresh_token=body.refresh_token)
    except AuthError as exc:
        # Garbage/expired/wrong-kind token: refused at decode, nothing written.
        raise HTTPException(
            status_code=401, detail=exc.reason, headers={"WWW-Authenticate": "Bearer"}
        ) from exc
    if isinstance(result, LoginDenied):
        return _denied(result)
    return AccessTokenOut(access_token=result)


# ---- MFA (TOTP) for privileged accounts (§1B C6) ----


@router.get("/mfa", response_model=MfaStatusOut)
async def mfa_status(current: CurrentUserDep, mfa: MfaDep) -> MfaStatusOut:
    """Whether the signed-in account holds a CONFIRMED authenticator factor.

    Any authenticated caller may ask; a patient is simply never enrolled (patients
    cannot hold a factor), so their answer is always false.
    """
    return MfaStatusOut(enrolled=await mfa.enrolled(current.user_id))


@router.post("/mfa/enroll", response_model=MfaEnrollOut, status_code=201)
async def mfa_enroll(current: PrivilegedUserDep, mfa: MfaDep) -> MfaEnrollOut:
    """Start (or restart) TOTP enrollment for a clinician/ops account.

    The secret is stored ONLY vault-encrypted (SecretStore, ADR-0017) and returned
    here exactly once for the authenticator app; there is no re-read endpoint. The
    factor gates nothing until confirmed with a matching code.
    """
    try:
        enrollment = await mfa.enroll(user_id=current.user_id)
    except MfaApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    return MfaEnrollOut(otpauth_uri=enrollment.otpauth_uri, secret=enrollment.secret)


@router.post("/mfa/enroll/confirm", response_model=MfaStatusOut)
async def mfa_confirm_enrollment(
    body: MfaCodeIn, current: PrivilegedUserDep, mfa: MfaDep
) -> MfaStatusOut:
    """Prove the authenticator holds the secret: a matching code activates the factor."""
    try:
        await mfa.confirm_enrollment(user_id=current.user_id, code=body.code)
    except MfaApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    return MfaStatusOut(enrolled=True)


@router.post("/mfa/verify", response_model=TokenOut)
async def mfa_verify(body: MfaVerifyIn, mfa: MfaDep) -> TokenOut | JSONResponse:
    """The login step-up: exchange the short-lived mfa_pending token + the 6-digit
    code for the real tokens. Anonymous — the pending token rides in the body and is
    refused everywhere a bearer token is expected (kind enforcement). Wrong codes
    are audited and throttled (§1B C5); the refusal is returned, never raised.
    """
    try:
        result = await mfa.verify_login(mfa_pending_token=body.mfa_pending_token, code=body.code)
    except AuthError as exc:
        # Not a signature-valid mfa_pending token (or an access/refresh token posted
        # here — the kind check refuses it): nothing written, plain 401.
        raise HTTPException(
            status_code=401, detail=exc.reason, headers={"WWW-Authenticate": "Bearer"}
        ) from exc
    if isinstance(result, LoginDenied):
        return _denied(result)
    return TokenOut(access_token=result.access_token, refresh_token=result.refresh_token)


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
