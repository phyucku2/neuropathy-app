"""MfaFactor — one enrolled TOTP factor per privileged user (§1B C6).

The row NEVER holds the TOTP secret: ``secret_ref`` is an opaque reference into the
SecretStore vault (encrypted at rest in Postgres when SECRET_STORE_KEY is configured —
the same seam EMR OAuth tokens use, ADR-0017). ``confirmed_at`` gates enforcement: an
enrollment only counts — and only steps up login — once the user has proven the
authenticator app produces matching codes, so an abandoned enrollment can never lock
an account out.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class MfaFactor(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "mfa_factor"

    # One factor per user (unique): re-enrollment REPLACES the row (and deletes the
    # superseded vault secret) rather than accumulating stale factors.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False, unique=True, index=True
    )

    # Opaque vault reference (same 200-char budget as emr_connection.token_ref) — the
    # secret itself lives behind the SecretStore seam, never in this table.
    secret_ref: Mapped[str] = mapped_column(String(200), nullable=False)

    # Set when the user confirms enrollment with a valid code; NULL = pending.
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
