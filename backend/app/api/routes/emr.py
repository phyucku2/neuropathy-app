"""EMR endpoints: provider registry, SMART connect/callback, pull, revoke (ADR-0009).

Routes are thin: validation + HTTP mapping only; the flow lives in EmrService. The
service is injected so tests (and later the DB-backed implementation) swap it without
touching this layer.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import (
    CurrentUser,
    PatientUserDep,
    get_emr_service,
    require_capability,
)
from app.api.deps import (
    EmrServiceDep as ServiceDep,
)
from app.emr.providers import get_provider, search_providers
from app.emr.service import ConnectionRecord, EmrError, EmrService
from app.schemas.emr import (
    ConnectionOut,
    ConnectStartIn,
    ConnectStartOut,
    ProviderOut,
    PullNotesOut,
    PullOut,
)

__all__ = ["get_emr_service", "router"]

router = APIRouter(prefix="/emr", tags=["emr"])


def _to_out(record: ConnectionRecord) -> ConnectionOut:
    return ConnectionOut(
        id=record.id,
        patient_id=record.patient_id,
        fhir_base=record.fhir_base,
        provider_name=record.provider_name,
        status=record.status.value,
        granted_scope=record.granted_scope,
        patient_fhir_id=record.patient_fhir_id,
        token_expires_at=record.token_expires_at,
        revoked_at=record.revoked_at,
    )


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers(q: str = "") -> list[ProviderOut]:
    return [
        ProviderOut(
            key=p.key,
            name=p.name,
            vendor=p.vendor,
            sandbox_fhir_base=p.sandbox_fhir_base,
            note=p.note,
        )
        for p in search_providers(q)
    ]


async def _owned_connection(
    service: EmrService, connection_id: uuid.UUID, current: CurrentUser
) -> ConnectionRecord:
    """Fetch the connection and enforce ownership (cross-user access -> 404).

    404 — never 403 — for someone else's connection, byte-identical to the unknown-id
    answer (the house 404-over-403 posture, mirrors clinic.py/medications.py): a 403
    would confirm to any authenticated caller that a leaked connection UUID is a live
    record in the system. No existence leak."""
    try:
        record = await service.get_connection(connection_id)
    except EmrError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    if record.patient_id != current.patient_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    return record


# emr_connect gates ESTABLISHING/REFRESHING an EMR connection (ADR-0020): a patient
# turning it off prevents NEW connections and completing a handshake. It deliberately
# does NOT gate the pull (ingest_labs governs the data write) or revoke (revocation must
# never be toggle-blockable) — the connect-vs-pull split keeps "stop connecting" and
# "stop importing" as independent controls. Both connect and callback are gated because
# the callback is the connection-establishing step of the same flow.
@router.post(
    "/connect",
    response_model=ConnectStartOut,
    dependencies=[Depends(require_capability("emr_connect"))],
)
async def start_connect(
    body: ConnectStartIn, service: ServiceDep, current: PatientUserDep
) -> ConnectStartOut:
    fhir_base = body.fhir_base
    provider_name = None
    if body.provider_key is not None:
        provider = get_provider(body.provider_key)
        if provider is None:
            raise HTTPException(status_code=404, detail="Unknown provider key")
        provider_name = provider.name
        # Until per-organization production endpoints are registered, registry entries
        # connect against the vendor sandbox (ADR-0009).
        fhir_base = fhir_base or provider.sandbox_fhir_base
        if fhir_base is None:
            raise HTTPException(
                status_code=422,
                detail="Provider has no public sandbox; supply fhir_base explicitly",
            )
    assert fhir_base is not None  # guaranteed by ConnectStartIn validator + above
    assert current.patient_id is not None  # guaranteed by require_patient
    try:
        record, url, state = await service.start_connect(
            patient_id=current.patient_id,
            fhir_base=fhir_base,
            provider_name=provider_name,
            include_notes=body.connect_notes,
        )
    except EmrError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    return ConnectStartOut(connection_id=record.id, authorize_url=url, state=state)


@router.get(
    "/callback",
    response_model=ConnectionOut,
    dependencies=[Depends(require_capability("emr_connect"))],
)
async def oauth_callback(
    state: str, code: str, service: ServiceDep, current: PatientUserDep
) -> ConnectionOut:
    # The app forwards code+state after the EMR redirect; the single-use state ties the
    # exchange to the connect this same user started.
    try:
        record = await service.complete_callback(state=state, code=code)
    except EmrError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    if record.patient_id != current.patient_id:
        # Same 404 body as an unknown/expired state: another user's state must be
        # indistinguishable from a nonexistent one (no existence leak, never 403).
        raise HTTPException(status_code=404, detail="Unknown, expired, or already-used state")
    return _to_out(record)


# The pull writes lab Observations — the SAME data class as POST /labs — so the
# ingest_labs toggle and its kill switch govern both writers (ADR-0013 review
# finding: an ungated pull would defeat a clinician's ingest_labs=off order).
# Connect/callback/revoke stay ungated: revocation must never be toggle-blockable.
@router.post(
    "/connections/{connection_id}/pull",
    response_model=PullOut,
    dependencies=[Depends(require_capability("ingest_labs"))],
)
async def pull_labs(
    connection_id: uuid.UUID, service: ServiceDep, current: PatientUserDep
) -> PullOut:
    await _owned_connection(service, connection_id, current)
    try:
        results, imported, skipped = await service.pull_labs(connection_id)
    except EmrError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    # `imported` counts newly persisted Observations; re-pulls are idempotent, so a
    # second sync of the same records reports imported=0 while still returning them.
    # `skipped` counts un-mappable EHR entries that were passed over (never fatal).
    return PullOut(imported=imported, skipped=skipped, results=results)


# The clinical-note pull writes to the SEPARATE append-only note store (metadata only) —
# gated by its OWN opt-in toggle (ingest_notes), distinct from ingest_labs, so a patient
# can import labs without notes (or vice versa). Behind _owned_connection like the lab
# pull (cross-user -> non-enumerating 404). Connect/callback/revoke stay ungated as before.
@router.post(
    "/connections/{connection_id}/pull-notes",
    response_model=PullNotesOut,
    dependencies=[Depends(require_capability("ingest_notes"))],
)
async def pull_clinical_notes(
    connection_id: uuid.UUID, service: ServiceDep, current: PatientUserDep
) -> PullNotesOut:
    await _owned_connection(service, connection_id, current)
    try:
        fetched, imported, skipped = await service.pull_clinical_notes(connection_id)
    except EmrError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    # Counts only — no note text ever leaves the endpoint (NON-DIAGNOSTIC house rule).
    # `imported` counts newly persisted notes; re-pulls are idempotent (imported=0).
    return PullNotesOut(imported=imported, skipped=skipped, fetched=fetched)


@router.delete("/connections/{connection_id}", response_model=ConnectionOut)
async def revoke_connection(
    connection_id: uuid.UUID, service: ServiceDep, current: PatientUserDep
) -> ConnectionOut:
    # _owned_connection guarantees existence + ownership; revoke cannot fail after it.
    await _owned_connection(service, connection_id, current)
    return _to_out(await service.revoke(connection_id))
