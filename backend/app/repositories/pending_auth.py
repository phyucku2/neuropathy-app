"""Pending-auth store — interface + in-memory implementation (ADR-0017).

One entry per in-flight SMART OAuth handshake, keyed by its `state`: the connect and
callback requests arrive separately, so this state must outlive a request — and, in
DB mode, the process (PostgresPendingAuthStore in repositories/postgres.py).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app.core.config import settings

__all__ = ["InMemoryPendingAuthStore", "PendingAuth", "PendingAuthStore", "pending_auth_ttl"]


@dataclass(frozen=True)
class PendingAuth:
    """One in-flight PKCE exchange, keyed by its OAuth `state` in a PendingAuthStore."""

    connection_id: uuid.UUID
    code_verifier: str
    token_endpoint: str


def pending_auth_ttl() -> timedelta:
    """How long a started handshake may wait for its callback (settings-driven)."""
    return timedelta(seconds=settings.pending_auth_ttl_seconds)


class PendingAuthStore(Protocol):
    """state -> pending PKCE exchange, spanning the connect and callback requests.

    Contract (ADR-0017): entries expire pending_auth_ttl() after `put`, and `consume`
    is SINGLE-USE — of any number of callbacks presenting the same state, exactly one
    receives the PendingAuth; the rest (replays, races) get None.
    """

    async def put(self, state: str, pending: PendingAuth, *, now: datetime) -> None:
        """Store a started handshake; it expires pending_auth_ttl() after `now`."""
        ...

    async def consume(self, state: str, *, now: datetime) -> PendingAuth | None:
        """Atomically take the handshake for `state`: None if unknown, already
        consumed, or expired (expired entries are purged, never honored)."""
        ...


class InMemoryPendingAuthStore:
    """Dict-backed store for unit tests, DB-less development, and single-process
    deployments (deps wiring keeps ONE instance per process so connect and callback
    meet). dict operations are atomic under asyncio — no await between check and pop."""

    def __init__(self) -> None:
        self._pending: dict[str, tuple[PendingAuth, datetime]] = {}

    async def put(self, state: str, pending: PendingAuth, *, now: datetime) -> None:
        # Opportunistic purge, mirroring the Postgres store: expired handshakes never
        # accumulate beyond one put cycle.
        self._pending = {s: v for s, v in self._pending.items() if v[1] > now}
        self._pending[state] = (pending, now + pending_auth_ttl())

    async def consume(self, state: str, *, now: datetime) -> PendingAuth | None:
        entry = self._pending.pop(state, None)
        if entry is None:
            return None
        pending, expires_at = entry
        return pending if expires_at > now else None
