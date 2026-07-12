"""Observation — the unified longitudinal record at the center of the product.

Every ingested datum from every source (BioMech recording, lab result, ADL entry)
normalizes into an Observation. The schema is **research grade** (ADR-0006,
docs/engineering/data-standards.md): ALCOA+ integrity, immutable/append-only with
corrections-as-new-records, full provenance, dual timestamps, and standardized coding.

The authoritative full schema is still a dedicated data-model ADR; this carries the
research-grade essentials so no datum is captured without them.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class SourceType(enum.StrEnum):
    lab = "lab"  # patient-imported lab result (FHIR/LOINC/UCUM — ADR-0007)
    adl = "adl"  # activities-of-daily-living / functional status (patient-reported)
    # NOTE: BioMech is a separate module built later (ADR-0007); it will register its
    # own source when that module lands. Not part of the core data model now.


class DataOrigin(enum.StrEnum):
    """How the datum came to exist — its provenance class (ALCOA: Attributable)."""

    device_measured = "device_measured"  # from an instrument (e.g. BioMech sensor)
    document_imported = "document_imported"  # extracted from an imported doc (e.g. lab PDF)
    ehr_imported = "ehr_imported"  # pulled from the patient's EMR via SMART on FHIR
    patient_reported = "patient_reported"  # self-reported (e.g. ADL check-in)
    derived = "derived"  # computed from other observations


class ObservationStatus(enum.StrEnum):
    """Lifecycle status (FHIR-aligned). Values are never mutated; status transitions are.

    `entered_in_error` data is retained (ALCOA: Enduring) but excluded from analysis.
    """

    preliminary = "preliminary"  # captured, not yet confirmed (e.g. unconfirmed OCR)
    final = "final"  # confirmed, part of the record
    amended = "amended"  # updated with new information (new row supersedes)
    corrected = "corrected"  # fixed an error (new row supersedes)
    entered_in_error = "entered_in_error"  # should not exist — retained, not analyzed


class Observation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "observation"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )
    source: Mapped[SourceType] = mapped_column(Enum(SourceType, name="source_type"), nullable=False)
    origin: Mapped[DataOrigin] = mapped_column(Enum(DataOrigin, name="data_origin"), nullable=False)

    # A stable code for what this measures (e.g. "balance_score", "hba1c", "adl_katz")
    # plus the coding system it belongs to (labs -> LOINC). Unambiguous + poolable.
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    code_system: Mapped[str | None] = mapped_column(String(40), nullable=True)  # e.g. "LOINC"

    value_num: Mapped[float | None] = mapped_column(nullable=True)
    # qualitative results (e.g. "positive")
    value_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    unit_system: Mapped[str | None] = mapped_column(String(20), nullable=True)  # e.g. "UCUM"

    # Dual timestamps (ALCOA: Contemporaneous). effective_at = clinically about;
    # recorded_at = when it entered the system. Both tz-aware UTC.
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Integrity / immutability (ALCOA: Original, Enduring). Corrections are NEW rows that
    # supersede the row named by revises_id; values are never overwritten.
    status: Mapped[ObservationStatus] = mapped_column(
        Enum(ObservationStatus, name="observation_status"),
        nullable=False,
        default=ObservationStatus.final,
    )
    revises_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("observation.id"), nullable=True
    )

    # Attribution (ALCOA: Attributable) — who/what recorded it.
    recorded_by_role: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Quality/provenance detail: instrument/protocol version, device, method, extraction
    # confidence, calibration state, human_confirmed flag. Required, not optional.
    quality: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Full raw source payload (metric set / lab panel row / questionnaire answers).
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_observation_patient_code_time", "patient_id", "code", "effective_at"),
        Index("ix_observation_status", "status"),
    )
