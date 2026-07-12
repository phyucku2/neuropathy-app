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


@router.post("/connect", response_model=ConnectStartOut)
async def start_connect(body: ConnectStartIn, service: ServiceDep) -> ConnectStartOut:
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
    try:
        record, url, state = await service.start_connect(
            patient_id=body.patient_id, fhir_base=fhir_base, provider_name=provider_name
        )
    except EmrError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    return ConnectStartOut(connection_id=record.id, authorize_url=url, state=state)


@router.get("/callback", response_model=ConnectionOut)
async def oauth_callback(state: str, code: str, service: ServiceDep) -> ConnectionOut:
    try:
        record = await service.complete_callback(state=state, code=code)
    except EmrError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    return _to_out(record)


@router.post("/connections/{connection_id}/pull", response_model=PullOut)
async def pull_labs(connection_id: uuid.UUID, service: ServiceDep) -> PullOut:
    try:
        results = await service.pull_labs(connection_id)
    except EmrError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    # Persistence as research-grade Observations (origin=ehr_imported) lands with the
    # DB layer; until then the parsed results are returned to the caller.
    return PullOut(imported=len(results), results=results)


@router.delete("/connections/{connection_id}", response_model=ConnectionOut)
async def revoke_connection(connection_id: uuid.UUID, service: ServiceDep) -> ConnectionOut:
    try:
        record = service.revoke(connection_id)
    except EmrError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    return _to_out(record)
