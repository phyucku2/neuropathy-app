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

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, text
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


class CaregiverAlertType(enum.StrEnum):
    """The four caregiver alert kinds (ADR-0047 Phase B1). Scope-gated: a trends-only
    caregiver may see only missed_checkin + trend_shift (type_allowed_for_scope)."""

    missed_checkin = "missed_checkin"  # no ADL check-in within the missed window
    med_change = "med_change"  # a medication change/event landed
    trend_shift = "trend_shift"  # a weekly NSI/trajectory direction change (per code/ISO week)
    new_chart_note = "new_chart_note"  # a new EMR clinical note (DocumentReference) exists


class CaregiverAlert(UUIDPrimaryKey, Timestamps, Base):
    """One compute-on-read caregiver alert (ADR-0047 Phase B1) — an append-only fact.

    Evaluators persist candidate alerts idempotently via ``add_if_absent`` on the
    once-only-per-logical-event backstop ``uq_caregiver_alert_link_type_dedupe``: a
    re-read of the feed never duplicates a row (mirrors the observation/emr-note
    ``add_if_absent`` idempotency, but ``dedupe_key`` is NOT NULL for every type, so a
    plain composite UNIQUE is the faithful analog of the partial-unique import index).
    ``acknowledged_at`` is the one lifecycle mutation (a conditional UPDATE), so
    ``Timestamps`` is correct here just as it is on ``CaregiverAlertPreference``.
    """

    __tablename__ = "caregiver_alert"

    __table_args__ = (
        # Once-only per logical event: the same (link, type, dedupe_key) can never
        # produce a second row — the storage backstop ``add_if_absent`` absorbs as a
        # skip, exactly like uq_emr_note_patient_import_key. dedupe_key is NOT NULL for
        # every type, so a plain composite UNIQUE is the faithful analog (no partial WHERE).
        Index(
            "uq_caregiver_alert_link_type_dedupe",
            "caregiver_link_id",
            "alert_type",
            "dedupe_key",
            unique=True,
        ),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )
    # Alerts FK the caregiver_link (account deletion must remove them BEFORE the
    # caregiver_invite/caregiver_link rows — FK-safe order, ADR-0047 B1).
    caregiver_link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("caregiver_link.id"), nullable=False, index=True
    )
    alert_type: Mapped[CaregiverAlertType] = mapped_column(
        Enum(CaregiverAlertType, name="caregiver_alert_type"), nullable=False
    )
    # The per-type logical-event identity (ADR-0047 B1): trend_shift = "{code}:{ISO week}",
    # new_chart_note = the note's import_key, med_change = the med-change event id,
    # missed_checkin = the missed-window date key. NEVER a value — a reference only.
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    # Null = unacknowledged; set once by the caregiver's idempotent ack (a conditional
    # UPDATE ... WHERE acknowledged_at IS NULL, so a double-ack is a quiet no-op).
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaregiverAlertPreference(UUIDPrimaryKey, Timestamps, Base):
    """Per-patient, per-type caregiver-alert opt-in (ADR-0047 Phase B1) — DEFAULT OFF.

    One row per (patient, alert_type); ``uq_caregiver_alert_preference_patient_type``
    owns that invariant and enables the insert-first upsert (mirrors PatientCapability).
    A missing row means OFF: an alert is emitted/shown ONLY when the patient's
    preference for the type is ON, the type is allowed for the link's scope, AND the
    link is active+accepted (the single _may_caregiver_read consent gate).
    """

    __tablename__ = "caregiver_alert_preference"

    __table_args__ = (
        Index(
            "uq_caregiver_alert_preference_patient_type",
            "patient_id",
            "alert_type",
            unique=True,
        ),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )
    alert_type: Mapped[CaregiverAlertType] = mapped_column(
        Enum(CaregiverAlertType, name="caregiver_alert_type"), nullable=False
    )
    # DEFAULT OFF (ADR-0047 B1): both the Python-side default and the DB server_default
    # are false, so an unset preference never leaks an alert.
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
