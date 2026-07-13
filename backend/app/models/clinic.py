"""Clinic — the servicing organization a clinical connection points at (ADR-0005).

Minimal by design: identity and display name. Clinician users link to their clinic
via ``app_user.clinic_id``; patients link through ``ClinicConnection`` records, whose
consent state — not this row — gates every data flow (ADR-0012).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class Clinic(UUIDPrimaryKey, Base):
    __tablename__ = "clinic"

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
