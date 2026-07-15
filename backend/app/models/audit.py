"""Audit event — append-only log of PHI access and capability/config changes.

Required by our health-data posture (CLAUDE.md §5): reads and writes of health data,
and every toggle/config change (which in the clinical version is order-like), are
logged. One pipeline serves HIPAA, SOC 2, and later research/FDA evidence needs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class AuditEvent(UUIDPrimaryKey, Base):
    __tablename__ = "audit_event"
    __table_args__ = (
        # The sliding-window rate-limit counter reads (actor, action, occurred_at)
        # on every gated request — keep it an index range scan (ADR-0017).
        Index("ix_audit_event_actor_action_time", "actor_id", "action", "occurred_at"),
    )

    # Append-only: created only, never updated. No updated_at by design.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_role: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # patient/clinician/ops/system

    action: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # e.g. read_observation, toggle_capability
    # ON DELETE SET NULL (migration 0006, ADR-0027): audit events are RETAINED under
    # regulatory retention when a patient account is deleted — they are PHI-free by
    # contract, so history survives as anonymous events instead of blocking (or being
    # cascaded away with) the deletion.
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patient.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Context: what was accessed/changed (ids, before/after for toggles). No secrets, no
    # raw PHI values — references, not payloads.
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
