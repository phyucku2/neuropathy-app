"""MFA factor repository — interface + in-memory implementation (§1B C6).

`MfaFactorRecord` is the storage-agnostic twin of `models.MfaFactor` the MFA service
works with; the Postgres implementation (repositories/postgres.py) maps it to the ORM
row. The record carries only the opaque `secret_ref` into the SecretStore vault —
the TOTP secret itself never passes through this layer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class MfaFactorRecord:
    """Storage-agnostic twin of models.MfaFactor (one factor per user)."""

    id: uuid.UUID
    user_id: uuid.UUID
    # Opaque vault reference — the secret lives behind the SecretStore seam only.
    secret_ref: str
    # Set once the user proves the authenticator produces matching codes; None =
    # pending enrollment, which never steps up login and never enforces.
    confirmed_at: datetime | None = None


class MfaFactorRepository(Protocol):
    """Persistence contract for the one-factor-per-user TOTP enrollment state."""

    async def get_for_user(self, user_id: uuid.UUID) -> MfaFactorRecord | None:
        """This user's factor (pending or confirmed), or None when unenrolled."""
        ...

    async def replace_for_user(self, user_id: uuid.UUID, *, secret_ref: str) -> str | None:
        """Insert the user's factor, replacing any existing one (re-enrollment always
        starts a FRESH, unconfirmed factor — a superseded factor must never keep
        stepping up login). Returns the superseded row's secret_ref so the caller can
        purge the old vault entry, or None when this was a first enrollment. The
        replacement is storage-serialized (DELETE ... RETURNING + the user_id unique
        index in Postgres) — never check-then-write (docs/lessons.md)."""
        ...

    async def confirm(self, user_id: uuid.UUID, *, at: datetime) -> MfaFactorRecord | None:
        """Mark the user's factor confirmed at `at` (idempotent — a re-confirm keeps
        the original timestamp). Returns the updated record, or None when the user
        has no factor to confirm."""
        ...


class InMemoryMfaFactorRepository:
    """Dict-backed store for unit tests and DB-less development."""

    def __init__(self) -> None:
        self._by_user: dict[uuid.UUID, MfaFactorRecord] = {}

    async def get_for_user(self, user_id: uuid.UUID) -> MfaFactorRecord | None:
        return self._by_user.get(user_id)

    async def replace_for_user(self, user_id: uuid.UUID, *, secret_ref: str) -> str | None:
        superseded = self._by_user.get(user_id)
        self._by_user[user_id] = MfaFactorRecord(
            id=uuid.uuid4(), user_id=user_id, secret_ref=secret_ref, confirmed_at=None
        )
        return None if superseded is None else superseded.secret_ref

    async def confirm(self, user_id: uuid.UUID, *, at: datetime) -> MfaFactorRecord | None:
        record = self._by_user.get(user_id)
        if record is None:
            return None
        if record.confirmed_at is None:
            record.confirmed_at = at
        return record
