"""PendingAuthState — one in-flight SMART OAuth handshake, keyed by `state` (ADR-0017).

The connect and callback requests arrive separately (and, with multiple workers, on
different processes), so the state->PKCE-verifier mapping must be durable. Rows are
short-lived by design: they expire after settings.pending_auth_ttl_seconds and are
consumed (deleted) atomically by the first callback that presents the state —
single-use is what makes the state a CSRF/replay guard (ADR-0008).

The code verifier is stored in the clear: it is not a bearer credential (useless
without the intercepted authorization code AND our client identity), lives for
minutes, and is deleted on first use — encrypting it would gate the login flow on the
secret-store key without a matching threat (ADR-0017).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PendingAuthState(Base):
    __tablename__ = "pending_auth"

    # The OAuth `state` value itself — globally unique by construction (token_urlsafe).
    state: Mapped[str] = mapped_column(String(128), primary_key=True)

    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emr_connection.id"), nullable=False
    )
    code_verifier: Mapped[str] = mapped_column(String(256), nullable=False)
    token_endpoint: Mapped[str] = mapped_column(String(400), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Hard TTL: consume() refuses rows past this instant and purges opportunistically.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
