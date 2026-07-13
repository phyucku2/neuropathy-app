"""ClinicConnection — the link between a patient and a servicing clinic (ADR-0005).

Models the real lifecycle of a clinical connection: invited/requested (pending),
consented (active, data may flow), and revoked (data flow stopped). Consent gates all
transmission — no patient data reaches a clinic until `consent_granted_at` is set on an
active connection, regardless of what a clinician has toggled on (HIPAA; ADR-0003).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class ConnectionStatus(enum.StrEnum):
    pending = "pending"  # invited/requested, not yet consented — no data flows
    active = "active"  # consented — data may flow to the clinic
    revoked = "revoked"  # patient revoked — data flow stopped


class Initiator(enum.StrEnum):
    clinic = "clinic"  # clinic-initiated (invite/create)
    patient = "patient"  # patient-initiated (link code / provider selection)


class ClinicConnection(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "clinic_connection"

    # At most ONE live (non-revoked) connection per patient-clinic pair, enforced in
    # storage: the invite flow's check-then-insert cannot hold under concurrent
    # requests, and a duplicate that slipped through would keep data flowing after
    # the patient revoked "the" connection (ADR-0012 review finding).
    __table_args__ = (
        Index(
            "uq_clinic_connection_live",
            "patient_id",
            "clinic_id",
            unique=True,
            postgresql_where=text("status != 'revoked'"),
        ),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinic.id"), nullable=False, index=True
    )

    status: Mapped[ConnectionStatus] = mapped_column(
        Enum(ConnectionStatus, name="connection_status"),
        nullable=False,
        default=ConnectionStatus.pending,
    )
    initiated_by: Mapped[Initiator] = mapped_column(
        Enum(Initiator, name="initiator"), nullable=False
    )

    # Data flow is gated on this being set (and status == active). Null = no flow.
    consent_granted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
