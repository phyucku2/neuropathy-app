"""Capability registry + per-patient activation — the toggle authority model.

Every feature is a Capability. Whether it's on for a patient is a PatientCapability
row. Authority differs by version (Brainstorm #2):
  - B2C: the patient controls activation.
  - Clinical: the clinician controls activation (modeled with optional expiry, like an
    order — BioMech Lab review).
The API enforces this server-side; client toggles are only UI hints.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class Actor(enum.StrEnum):
    patient = "patient"
    clinician = "clinician"
    ops = "ops"


class Capability(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "capability"

    # Stable key, e.g. "ingest_biomech", "ingest_labs", "adl_checkin", "ai_trajectory".
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Ops-level availability kill switch (is this offered at all?).
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PatientCapability(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "patient_capability"
    __table_args__ = (
        UniqueConstraint("patient_id", "capability_id", name="uq_patient_capability"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )
    capability_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capability.id"), nullable=False
    )

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Who set this state, and (clinical) when it expires — renewal like an order.
    set_by: Mapped[Actor] = mapped_column(Enum(Actor, name="actor"), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
