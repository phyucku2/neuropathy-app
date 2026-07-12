"""EMR endpoints: provider registry, SMART connect/callback, pull, revoke (ADR-0009).

Routes are thin: validation + HTTP mapping only; the flow lives in EmrService. The
service is injected so tests (and later the DB-backed implementation) swap it without
touching this layer.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import CurrentUser, PatientUserDep
from app.core.config import settings
from app.emr.providers import get_provider, search_providers
from app.emr.service import ConnectionRecord, EmrError, EmrService
from app.emr.transport import HttpxTransport
from app.schemas.emr import ConnectionOut, ConnectStartIn, ConnectStartOut, ProviderOut, PullOut

router = APIRouter(prefix="/emr", tags=["emr"])


@lru_cache(maxsize=1)
def _default_service() -> EmrService:
    return EmrService(
        transport=HttpxTransport(),
        client_id=settings.smart_client_id or "unconfigured-client",
        redirect_uri=settings.smart_redirect_uri or "http://localhost:8000/emr/callback",
    )


def get_emr_service() -> EmrService:
    return _default_service()


ServiceDep = Annotated[EmrService, Depends(get_emr_service)]


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
    """Fetch the connection and enforce ownership (cross-user access -> 403)."""
    try:
        record = await service.get_connection(connection_id)
    except EmrError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    if record.patient_id != current.patient_id:
        raise HTTPException(status_code=403, detail="Not your connection")
    return record


@router.post("/connect", response_model=ConnectStartOut)
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
            patient_id=current.patient_id, fhir_base=fhir_base, provider_name=provider_name
        )
    except EmrError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    return ConnectStartOut(connection_id=record.id, authorize_url=url, state=state)


@router.get("/callback", response_model=ConnectionOut)
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
        raise HTTPException(status_code=403, detail="Not your connection")
    return _to_out(record)


@router.post("/connections/{connection_id}/pull", response_model=PullOut)
async def pull_labs(
    connection_id: uuid.UUID, service: ServiceDep, current: PatientUserDep
) -> PullOut:
    await _owned_connection(service, connection_id, current)
    try:
        results, imported = await service.pull_labs(connection_id)
    except EmrError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    # `imported` counts newly persisted Observations; re-pulls are idempotent, so a
    # second sync of the same records reports imported=0 while still returning them.
    return PullOut(imported=imported, results=results)


@router.delete("/connections/{connection_id}", response_model=ConnectionOut)
async def revoke_connection(
    connection_id: uuid.UUID, service: ServiceDep, current: PatientUserDep
) -> ConnectionOut:
    # _owned_connection guarantees existence + ownership; revoke cannot fail after it.
    await _owned_connection(service, connection_id, current)
    return _to_out(await service.revoke(connection_id))
