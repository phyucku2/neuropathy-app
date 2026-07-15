"""API contract for the patient data export — "Download my data" (ADR-0031).

The right-of-access companion to account deletion (ADR-0027): the patient's COMPLETE
record, assembled from the same read paths every other endpoint uses, serialized as
one typed envelope.

NO SECRETS, EVER. The sub-models below carry only non-secret projections: the account
profile has no password hash, the EMR-connection model reuses the token-free
`schemas.emr.ConnectionOut` (it has no `token_ref` field at all, so a vault reference
can never be serialized), and clinic connections reuse `schemas.clinic.ConnectionOut`.
The absence is structural — there is no field to leak into — and is proven by tests
that scan the serialized payload for the known token/hash fixtures (ADR-0031).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.capability import CapabilityStateOut
from app.schemas.clinic import ConnectionOut as ClinicConnectionOut
from app.schemas.emr import ConnectionOut as EmrConnectionOut
from app.schemas.trajectory import Trajectory

# Bump on any breaking shape change so a downloaded file stays interpretable by later
# tooling (forward-compat, ADR-0031). The envelope always carries this string.
EXPORT_SCHEMA_VERSION = "1.0"


class ExportAccountProfile(BaseModel):
    """The authentication identity (models.User) — NEVER the password hash."""

    display_name: str
    email: str
    role: str
    created_at: datetime | None


class ExportPatient(BaseModel):
    """The linked clinical record (models.Patient) — non-secret fields only."""

    patient_id: uuid.UUID
    display_name: str
    connection_mode: str
    created_at: datetime | None


class ExportObservation(BaseModel):
    """One research-grade observation with full provenance (models.Observation).

    Source, origin, dual timestamps, coding, values, and the quality/payload detail —
    the patient's own health data, which is exactly what a right-of-access export must
    contain. No token or secret material is part of an observation.
    """

    id: uuid.UUID
    source: str
    origin: str
    code: str
    code_system: str | None
    value_num: float | None
    value_text: str | None
    unit: str | None
    unit_system: str | None
    effective_at: datetime
    recorded_at: datetime
    status: str
    revises_id: uuid.UUID | None
    recorded_by_role: str | None
    quality: dict[str, Any]
    payload: dict[str, Any]


class ExportOut(BaseModel):
    """The complete export envelope for one patient (ADR-0031)."""

    # Envelope (ADR-0031): when the file was produced, the shape version for
    # forward-compat, and whose record it is.
    exported_at: datetime
    schema_version: str = Field(default=EXPORT_SCHEMA_VERSION)
    subject_id: uuid.UUID

    account: ExportAccountProfile
    patient: ExportPatient
    observations: list[ExportObservation]
    trajectory: Trajectory
    capabilities: list[CapabilityStateOut]
    clinic_connections: list[ClinicConnectionOut]
    emr_connections: list[EmrConnectionOut]
