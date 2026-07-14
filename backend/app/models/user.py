"""User — the authentication identity, distinct from the Patient clinical record
(ADR-0010). A patient user links to its Patient row via patient_id; an ops user
(UserRole.ops) carries neither patient_id nor clinic_id — it is a pure operator
principal for the provisioning surface (ADR-0019).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class UserRole(enum.StrEnum):
    patient = "patient"
    clinician = "clinician"
    ops = "ops"


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "app_user"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False, default=UserRole.patient
    )

    # Set for patient users; clinician/ops users have no patient record.
    patient_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Set for clinician users: the clinic every clinical query is scoped to (ADR-0012).
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinic.id"), nullable=True
    )

    # Per-account revocation (ADR-0019): a deactivated account fails login and every
    # role gate. Introduced for ops operators (per-operator revocation the shared
    # bootstrap token never had), but the flag is general — any account can be
    # disabled. server_default=true so the migration can add it NOT NULL and every
    # existing row (and every account that predates a deactivation) is active.
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
