"""Caregiver Companion Phase A — invite + link models (ADR-0047).

The caregiver relationship reuses the patient-held consent primitive built for
clinicians (ADR-0012/0020) with a new grantee: the patient generates an invite code,
the loved one claims it, and the resulting link stays PENDING until the patient
explicitly accepts — double opt-in, nothing visible before acceptance. The lifecycle
(pending → active → revoked) and the partial-unique live-link index mirror
ClinicConnection (models/connection.py); the index is per (patient, caregiver) pair,
so unlimited caregivers per patient hold.

The invite CODE is never stored: only its sha256 hex lands in `code_hash`
(the stdlib-hash idiom services/auth.py already uses for throttle sentinels). The
plaintext is returned exactly once at creation. Codes expire and are single-use.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.connection import Initiator


class CaregiverScope(enum.StrEnum):
    """What the patient lets THIS caregiver see (ADR-0047, per-caregiver scope)."""

    trends = "trends"  # wellness trend + direction only
    full = "full"  # trends + the Visit-Ready Summary surfaces


class CaregiverLinkStatus(enum.StrEnum):
    pending = "pending"  # code claimed, awaiting the PATIENT's acceptance — no data flows
    active = "active"  # patient accepted — reads may flow within scope
    revoked = "revoked"  # patient revoked/declined — data flow stopped


class CaregiverInvite(UUIDPrimaryKey, Timestamps, Base):
    """One patient-generated, expiring, single-use caregiver invite code (hashed)."""

    __tablename__ = "caregiver_invite"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )
    # sha256 hex of the normalized code — the code itself is NEVER stored (lookup is
    # by hash, verification never needs decryption, so the Fernet vault is the wrong
    # seam). Unique: one hash can only ever name one invite.
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Single-use marker: set when a caregiver claims the code.
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Patient cancellation: a cancelled code can never be claimed.
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaregiverLink(UUIDPrimaryKey, Timestamps, Base):
    """The patient↔caregiver consent link (ADR-0047), mirroring ClinicConnection."""

    __tablename__ = "caregiver_link"

    # At most ONE live (non-revoked) link per patient-caregiver PAIR, enforced in
    # storage exactly like uq_clinic_connection_live: the claim flow's
    # check-then-insert cannot hold under concurrent requests. Per-pair, so a patient
    # may hold unlimited caregivers (ADR-0047).
    __table_args__ = (
        Index(
            "uq_caregiver_link_live",
            "patient_id",
            "caregiver_user_id",
            unique=True,
            postgresql_where=text("status != 'revoked'"),
        ),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )
    caregiver_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False, index=True
    )

    scope: Mapped[CaregiverScope] = mapped_column(
        Enum(CaregiverScope, name="caregiver_scope"),
        nullable=False,
        default=CaregiverScope.trends,
    )
    status: Mapped[CaregiverLinkStatus] = mapped_column(
        Enum(CaregiverLinkStatus, name="caregiver_link_status"),
        nullable=False,
        default=CaregiverLinkStatus.pending,
    )
    # Always patient: the invite code is the patient's act; reuses the existing
    # `initiator` enum type (no clinic-initiated caregiver links exist).
    initiated_by: Mapped[Initiator] = mapped_column(
        Enum(Initiator, name="initiator"), nullable=False, default=Initiator.patient
    )

    # Data flow is gated on this being set (and status == active) — the double
    # opt-in's second step. Null = the patient has not accepted, nothing flows.
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
