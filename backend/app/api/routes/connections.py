"""Patient-side clinic connection endpoints: list, consent, revoke (ADR-0005/0012).

The patient owns the consent lifecycle: a clinic invitation stays pending until the
patient grants consent here, and the patient can revoke at any time — data flow to
the clinic stops immediately. Ownership failures answer 404 (not 403): another
patient's connection id must be indistinguishable from a nonexistent one.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from app.api.deps import ClinicServiceDep, PatientUserDep
from app.models.clinic import Clinic
from app.models.connection import ClinicConnection
from app.schemas.clinic import ConnectionOut

router = APIRouter(prefix="/connections", tags=["connections"])


def _to_out(connection: ClinicConnection, clinic: Clinic | None) -> ConnectionOut:
    return ConnectionOut(
        id=connection.id,
        clinic_id=connection.clinic_id,
        clinic_name=clinic.name if clinic is not None else "Unknown clinic",
        status=connection.status.value,
        initiated_by=connection.initiated_by.value,
        consent_granted_at=connection.consent_granted_at,
        revoked_at=connection.revoked_at,
    )


@router.get("", response_model=list[ConnectionOut])
async def list_connections(
    current: PatientUserDep, service: ClinicServiceDep
) -> list[ConnectionOut]:
    """The patient's own clinic connections — status, clinic name, consent state."""
    assert current.patient_id is not None  # guaranteed by require_patient
    rows = await service.list_connections(current.patient_id)
    return [_to_out(connection, clinic) for connection, clinic in rows]


@router.post("/{connection_id}/consent", response_model=ConnectionOut)
async def grant_consent(
    connection_id: uuid.UUID, current: PatientUserDep, service: ClinicServiceDep
) -> ConnectionOut:
    """Grant consent on the patient's OWN pending connection: records the grant and
    activates it — only then may data flow to the clinic (ADR-0005). 404 for
    anything else (someone else's connection, unknown id, not pending)."""
    assert current.patient_id is not None  # guaranteed by require_patient
    connection = await service.grant_consent(
        patient_id=current.patient_id, actor_id=current.user_id, connection_id=connection_id
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    clinic = await service.clinics.get(connection.clinic_id)
    return _to_out(connection, clinic)


@router.delete("/{connection_id}", status_code=204)
async def revoke_connection(
    connection_id: uuid.UUID, current: PatientUserDep, service: ClinicServiceDep
) -> None:
    """Revoke the patient's own connection: data flow stops immediately. Idempotent —
    re-revoking answers 204 again; 404 only for connections that aren't theirs."""
    assert current.patient_id is not None  # guaranteed by require_patient
    connection = await service.revoke_connection(
        patient_id=current.patient_id, actor_id=current.user_id, connection_id=connection_id
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
