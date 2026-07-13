"""User — the authentication identity, distinct from the Patient clinical record
(ADR-0010). A patient user links to its Patient row via patient_id.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
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
