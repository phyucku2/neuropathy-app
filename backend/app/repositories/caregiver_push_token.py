"""Caregiver push-token repositories — interface + in-memory twin (ADR-0047 Phase B2),
mirroring repositories/caregiver_alert.py.

Both work directly with ``models.CaregiverPushToken`` — the device registration tokens
the register/deregister endpoints write and the FCM fan-out reads/prunes, so the same
rows storage holds are the ones the sender delivers to.

``upsert`` mirrors the observation/preference insert-first contract: the DB-level UNIQUE
index ``uq_caregiver_push_token_token`` is the real invariant, so a device re-registering
(or moving to another caregiver account) updates the one row in place rather than
duplicating it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from app.models.caregiver import CaregiverPushToken


class CaregiverPushTokenRepository(Protocol):
    """Persistence contract for caregiver device registration tokens."""

    async def upsert(
        self, *, caregiver_user_id: uuid.UUID, token: str, platform: str, now: datetime
    ) -> CaregiverPushToken:
        """Register or refresh a device token, keyed on the unique ``token``.

        Insert-first; on the ``uq_caregiver_push_token_token`` conflict, update the owning
        caregiver, platform, and ``last_seen_at`` in place (a device re-registering, a
        token refresh, or the same device moving to another caregiver account all resolve
        to the one row). Race-safe: the DB UNIQUE index guarantees one row per token even
        under concurrent requests."""
        ...

    async def list_for_caregiver(self, caregiver_user_id: uuid.UUID) -> list[CaregiverPushToken]:
        """Every device token for one caregiver (the FCM fan-out delivers to each)."""
        ...

    async def delete_by_token(self, token: str) -> None:
        """Delete one device token — deregister on logout/permission-off, and the
        ``UNREGISTERED`` cleanup the FCM fan-out runs. Idempotent (a missing token is a
        no-op)."""
        ...

    async def delete_for_caregiver(self, caregiver_user_id: uuid.UUID) -> None:
        """Destroy every device token for one caregiver account (its deletion). Runs
        BEFORE the user row dies (tokens FK ``app_user``)."""
        ...


class InMemoryCaregiverPushTokenRepository:
    """List-backed store for unit tests and DB-less development."""

    def __init__(self) -> None:
        self._rows: list[CaregiverPushToken] = []

    async def upsert(
        self, *, caregiver_user_id: uuid.UUID, token: str, platform: str, now: datetime
    ) -> CaregiverPushToken:
        # Mirror uq_caregiver_push_token_token: one row per token, updated in place.
        existing = next((r for r in self._rows if r.token == token), None)
        if existing is not None:
            existing.caregiver_user_id = caregiver_user_id
            existing.platform = platform
            existing.last_seen_at = now
            return existing
        row = CaregiverPushToken(
            id=uuid.uuid4(),
            caregiver_user_id=caregiver_user_id,
            token=token,
            platform=platform,
            last_seen_at=now,
        )
        # Column defaults (created_at/updated_at) only apply on a DB flush; mirror them.
        row.created_at = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
        row.updated_at = row.created_at
        self._rows.append(row)
        return row

    async def list_for_caregiver(self, caregiver_user_id: uuid.UUID) -> list[CaregiverPushToken]:
        return [r for r in self._rows if r.caregiver_user_id == caregiver_user_id]

    async def delete_by_token(self, token: str) -> None:
        self._rows = [r for r in self._rows if r.token != token]

    async def delete_for_caregiver(self, caregiver_user_id: uuid.UUID) -> None:
        self._rows = [r for r in self._rows if r.caregiver_user_id != caregiver_user_id]
