"""Patient — the person whose longitudinal record we aggregate.

Minimal by design: this skeleton models identity + tenancy only. The full data model
(consent, clinic membership, clinician links) is a dedicated ADR still to come.
"""
from __future__ import annotations

import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class Patient(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "patient"

    # Display name only; richer demographics live behind consent in a later model.
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Tenancy: null = B2C (self-managed). Set = belongs to a clinic (clinical version).
    # Every patient-scoped query MUST filter by patient_id; clinical queries also by clinic.
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
