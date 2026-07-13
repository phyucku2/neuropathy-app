"""Patient — the person whose longitudinal record we aggregate.

Minimal by design: identity, tenancy, and connection mode. The full data model
(demographics behind consent, clinician links) is a dedicated ADR still to come.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class ConnectionMode(enum.StrEnum):
    """How the account is linked (ADR-0005)."""

    self_connected = "self_connected"  # patient owns + manages their own account (B2C)
    clinical = "clinical"  # linked to a servicing clinic (clinician-configured)


class Patient(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "patient"

    # Display name only; richer demographics live behind consent in a later model.
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)

    connection_mode: Mapped[ConnectionMode] = mapped_column(
        Enum(ConnectionMode, name="connection_mode"),
        nullable=False,
        default=ConnectionMode.self_connected,
    )

    # RESERVED — not yet maintained. ClinicConnection (judged by
    # may_transmit_to_clinic) is the sole source of truth for clinic linkage; the
    # consent lifecycle (ADR-0012) does not write this column or flip
    # connection_mode, so neither may be queried until a lifecycle hook maintains
    # them. Every patient-scoped query MUST filter by patient_id.
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
