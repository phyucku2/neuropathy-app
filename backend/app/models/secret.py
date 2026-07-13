"""StoredSecret — the encrypted-at-rest OAuth token vault (ADR-0017).

Rows hold Fernet ciphertext ONLY (AES-128-CBC + HMAC, keyed by
settings.secret_store_key, which lives outside the repo and the database). Plaintext
tokens never touch the database: without a configured key the app keeps the
per-process in-memory vault instead — fail closed, never fail plaintext.
`emr_connection.token_ref` points at rows here; the ref is a random handle, not a key
derived from the secret.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StoredSecret(Base):
    __tablename__ = "secret"

    # The opaque reference stored on emr_connection.token_ref (same 200-char budget).
    ref: Mapped[str] = mapped_column(String(200), primary_key=True)

    # Fernet token (the encrypted secret material) — never plaintext.
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
