"""Ops-auth surface (ADR-0019): per-operator identities that replace the shared
OPS_BOOTSTRAP_TOKEN on the clinician-provisioning path.

Operators are real ops accounts (UserRole.ops) with their own Argon2id credentials;
they authenticate through the SAME /auth/login and carry role=ops in their JWT. Every
steady-state provisioning action is attributed to a named operator and each operator
can be revoked independently — none of which a single shared secret could do.

Two auth postures live on POST /accounts, and exactly one applies per request:

- **First-ops bootstrap** (zero ops accounts exist): the endpoint is unauthenticated
  and gated ONLY by OPS_BOOTSTRAP_TOKEN — the narrowed, last remaining use of that
  token. Same fail-closed + constant-time + denial-audited + denial-audit-rate-limited
  posture the clinician gate used to have, because this is the one surface an anonymous
  client can still reach. It self-closes permanently the moment any ops account exists.
- **Steady state** (an ops account already exists): the bootstrap token no longer
  opens anything here; a valid ops BEARER token is required (require_ops), so further
  operators are created by an authenticated, attributed operator.

Deactivation (POST /accounts/{id}/deactivate) is always require_ops, and refuses to
remove the last active operator — with the bootstrap gate closed, that would lock the
provisioning surface out entirely.
"""

from __future__ import annotations

import secrets as pysecrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import AuthDep, ClinicServiceDep, OpsUserDep, get_current_user, require_ops
from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.user import UserRole
from app.repositories.user import OpsDeactivateOutcome
from app.schemas.ops import OpsAccountCreateIn, OpsAccountOut
from app.services.auth import AuthApiError, AuthService
from app.services.clinic import (
    OPS_BOOTSTRAP_ACTOR_ID,
    ClinicService,
    bootstrap_denial_audit_limiter,
)

router = APIRouter(prefix="/ops", tags=["ops"])

# A second HTTPBearer instance (stateless) so POST /accounts can accept an OPTIONAL
# bearer: the first-ops bootstrap path has no token to present, the steady-state path
# requires one. auto_error=False lets us choose the posture from the ops-count, not
# from the presence of a header.
_optional_bearer = HTTPBearer(auto_error=False)

# ONE byte-identical denial for every POST /accounts request lacking the credential
# valid in the CURRENT bootstrap state — a missing/wrong bootstrap token before any ops
# exists, or a missing/wrong/non-ops bearer after (ADR-0019). The two branches otherwise
# answered differently (403 "Bootstrap token required" vs 401 "Missing bearer token"),
# which let an anonymous client read the status/body as an oracle for whether ops
# accounts exist. Same status + body across states closes that oracle; a genuine ops
# bearer (or a valid bootstrap token while zero ops exist) is the only way through.
_PROVISION_DENIED = {"detail": "Not authorized to create ops accounts"}


def _provision_denied() -> JSONResponse:
    return JSONResponse(status_code=403, content=_PROVISION_DENIED)


async def _first_ops_bootstrap_denial(
    provided: str | None, service: ClinicService, *, now: datetime
) -> JSONResponse | None:
    """The narrowed OPS_BOOTSTRAP_TOKEN gate — first-ops creation only (ADR-0019).

    Identical posture to the retired clinician gate (ADR-0017): fail closed when the
    token is unconfigured, constant-time compare, one byte-identical 403 for missing
    and wrong tokens, FAILED attempts audited (failure shape only, never token
    material) under the fixed sentinel actor, and that denial audit CAPPED by a
    sliding window — this endpoint is unauthenticated while zero ops exist, so
    unbounded per-request audit writes would hand an anonymous client a log-flood
    primitive against the PHI database. Beyond the budget the same 403 answers and only
    the audit write is skipped. The denial is RETURNED (not raised) so the audit event
    commits with the request transaction instead of rolling back.
    """
    configured = settings.ops_bootstrap_token
    if (
        configured
        and provided is not None
        and pysecrets.compare_digest(configured.encode(), provided.encode())
    ):
        return None
    if await bootstrap_denial_audit_limiter(service.audit).allow(OPS_BOOTSTRAP_ACTOR_ID, now=now):
        await service.audit.add(
            AuditEvent(
                actor_id=OPS_BOOTSTRAP_ACTOR_ID,
                actor_role="ops",
                action="bootstrap_denied",
                patient_id=None,
                # Never the tokens themselves — only the shape of the failure.
                detail={"configured": bool(configured), "token_presented": provided is not None},
            )
        )
    return _provision_denied()


async def _authenticated_ops(
    credentials: HTTPAuthorizationCredentials | None, auth: AuthService
) -> uuid.UUID:
    """Resolve the caller as an active ops operator, or raise (401/403) — the
    steady-state gate on POST /accounts. Reuses the shared get_current_user +
    require_ops so token/role/active semantics stay identical to every other gate."""
    current = require_ops(await get_current_user(credentials, auth))
    return current.user_id


@router.post("/accounts", response_model=OpsAccountOut, status_code=201)
async def create_ops_account(
    body: OpsAccountCreateIn,
    auth: AuthDep,
    service: ClinicServiceDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_optional_bearer)] = None,
    x_bootstrap_token: Annotated[str | None, Header()] = None,
) -> OpsAccountOut | JSONResponse:
    """Create an ops operator account.

    Zero ops accounts exist -> first-ops bootstrap (OPS_BOOTSTRAP_TOKEN required, and
    that gate then closes forever). Otherwise -> a valid ops bearer is required and the
    new account is attributed to that operator. A request lacking the credential valid
    for the current state gets one byte-identical denial either way (_provision_denied),
    so the branch is not an oracle for whether ops accounts exist."""
    now = datetime.now(UTC)
    bootstrap = not await auth.ops_account_exists()
    actor_id: uuid.UUID | None
    if not bootstrap:
        # Steady state: the shared token opens nothing here anymore — attributed ops
        # only. Any auth failure (no/invalid bearer, wrong role, deactivated) collapses
        # to the SAME denial the first-ops path returns, so the two states are
        # indistinguishable to a client without a valid credential.
        try:
            actor_id = await _authenticated_ops(credentials, auth)
        except HTTPException:
            return _provision_denied()
    else:
        # First operator: the one remaining, self-closing use of the bootstrap token.
        denial = await _first_ops_bootstrap_denial(x_bootstrap_token, service, now=now)
        if denial is not None:
            return denial
        actor_id = None
    try:
        if bootstrap:
            # Atomically guarded so two concurrent bootstraps can't both mint a "first"
            # operator (ADR-0019); the loser gets a 409.
            user = await auth.create_first_ops(
                email=body.email, password=body.password, display_name=body.display_name
            )
        else:
            user = await auth.create_ops(
                email=body.email, password=body.password, display_name=body.display_name
            )
    except AuthApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    # Provisioning an operator is a privileged config change — audited (CLAUDE.md §5).
    # bootstrap=True marks the self-closing first-ops creation (no authenticated actor).
    await service.audit.add(
        AuditEvent(
            actor_id=actor_id,
            actor_role="ops",
            action="create_ops",
            patient_id=None,
            detail={"user_id": str(user.id), "bootstrap": actor_id is None},
        )
    )
    return OpsAccountOut(
        user_id=user.id, email=user.email, display_name=user.display_name, active=user.active
    )


@router.post("/accounts/{user_id}/deactivate", response_model=OpsAccountOut)
async def deactivate_ops_account(
    user_id: uuid.UUID, current: OpsUserDep, auth: AuthDep, service: ClinicServiceDep
) -> OpsAccountOut:
    """Revoke one operator (ADR-0019): per-operator, immediate, and attributed.

    404 for a non-ops or unknown id. Idempotent — deactivating an already-disabled
    operator is a quiet success (no second audit event). Refuses (409) to remove the
    LAST active operator: with the bootstrap gate closed once any ops exists, that would
    lock provisioning out entirely.

    The last-active guard and the flip run as ONE atomic, lock-serialized step
    (deactivate_ops_guarded), so two concurrent deactivations cannot both pass the >1
    check and drive active ops to zero — the second sees the reduced count and 409s."""
    result = await auth.deactivate_ops_guarded(user_id)
    if result.outcome is OpsDeactivateOutcome.not_found:
        raise HTTPException(status_code=404, detail="Ops account not found")
    if result.outcome is OpsDeactivateOutcome.refused_last_active:
        raise HTTPException(status_code=409, detail="Cannot deactivate the last active ops account")
    record = result.record
    assert record is not None  # already_inactive and deactivated both carry the record
    if result.outcome is OpsDeactivateOutcome.deactivated:
        await service.audit.add(
            AuditEvent(
                actor_id=current.user_id,
                actor_role="ops",
                action="deactivate_ops",
                patient_id=None,
                detail={"user_id": str(user_id), "self": user_id == current.user_id},
            )
        )
    # already_inactive falls through: a quiet idempotent success, nothing new to record.
    return OpsAccountOut(
        user_id=record.id,
        email=record.email,
        display_name=record.display_name,
        active=record.active,
    )


@router.post("/accounts/{user_id}/reactivate", response_model=OpsAccountOut)
async def reactivate_ops_account(
    user_id: uuid.UUID, current: OpsUserDep, auth: AuthDep, service: ClinicServiceDep
) -> OpsAccountOut:
    """Restore a deactivated operator (ADR-0019 defense-in-depth): set active on, clear
    disabled_at, and let that operator log in again.

    A recovery path for an accidental over-deactivation without DB surgery — reactivation
    only ADDS an active operator, so it needs no lockout guard. 404 for a non-ops or
    unknown id. Idempotent — reactivating an already-active operator is a quiet success
    (no second audit event)."""
    target = await auth.get_user(user_id)
    if target is None or target.role is not UserRole.ops:
        raise HTTPException(status_code=404, detail="Ops account not found")
    if target.active:
        # Already active — idempotent success, nothing new to record.
        return OpsAccountOut(
            user_id=target.id,
            email=target.email,
            display_name=target.display_name,
            active=target.active,
        )
    updated = await auth.reactivate_ops(user_id)
    assert updated is not None  # get_user just found it under the same request/transaction
    await service.audit.add(
        AuditEvent(
            actor_id=current.user_id,
            actor_role="ops",
            action="reactivate_ops",
            patient_id=None,
            detail={"user_id": str(user_id), "self": user_id == current.user_id},
        )
    )
    return OpsAccountOut(
        user_id=updated.id,
        email=updated.email,
        display_name=updated.display_name,
        active=updated.active,
    )
