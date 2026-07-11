"""Observation — the unified longitudinal record at the center of the product.

Every ingested datum from every source (BioMech recording, lab result, ADL entry)
normalizes into an Observation: typed, timestamped, source-tagged, and carrying the
capability-state context that produced it (so trend analysis can condition on which
sources were active — Brainstorm #3). Heterogeneous per-source detail lives in JSONB.

This is a working skeleton; the authoritative schema is a dedicated data-model ADR
(FHIR-informed: labs map toward Observation/LOINC).
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
    biomech = "biomech"  # ingested from BioMech reports/feed
    lab = "lab"  # patient-imported lab result
    adl = "adl"  # activities-of-daily-living / functional status


class Observation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "observation"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )
    source: Mapped[SourceType] = mapped_column(Enum(SourceType, name="source_type"), nullable=False)

    # A stable code for what this measures (e.g. "balance_score", "hba1c", "adl_katz").
    # Lab codes should map toward LOINC where feasible (data-model ADR).
    code: Mapped[str] = mapped_column(String(80), nullable=False)

    value_num: Mapped[float | None] = mapped_column(nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # When the observation is *about* (the clinical event time), not when it was ingested.
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Full source payload (raw metric set / lab panel row / questionnaire answers) and
    # provenance (file id, parser version, extraction confidence, human-confirmed flag).
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_observation_patient_code_time", "patient_id", "code", "effective_at"),
    )
