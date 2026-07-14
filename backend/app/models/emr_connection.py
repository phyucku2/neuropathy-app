"""EmrConnection — a patient's authorized link to their EMR via SMART on FHIR (ADR-0008).

Holds connection metadata only. OAuth tokens are secrets kept behind the SecretStore
(encrypted at rest in the `secret` table when a key is configured — ADR-0017) and
referenced by `token_ref`; plaintext tokens never live in the DB or logs.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class EmrConnectionStatus(enum.StrEnum):
    authorizing = "authorizing"  # OAuth flow started, not yet completed
    active = "active"  # tokens held; pulls allowed
    revoked = "revoked"  # patient disconnected; no further pulls


class EmrConnection(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "emr_connection"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )

    # The EHR's FHIR base URL (the SMART `iss`/`aud`).
    fhir_base: Mapped[str] = mapped_column(String(400), nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    status: Mapped[EmrConnectionStatus] = mapped_column(
        Enum(EmrConnectionStatus, name="emr_connection_status"),
        nullable=False,
        default=EmrConnectionStatus.authorizing,
    )
    granted_scope: Mapped[str | None] = mapped_column(String(500), nullable=True)
    patient_fhir_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Reference into the SecretStore vault — NOT the tokens themselves.
    token_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
