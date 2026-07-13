"""Capability registry repository — interface + in-memory implementation (ADR-0013).

Works directly with `models.Capability` — the row whose `available` flag is the ops
kill switch the effective-state computation judges. Registry rows are created lazily
(get-or-create by key) by CapabilityService, so both storage modes work without seeds.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from app.models.capability import Capability


class DuplicateCapabilityKeyError(Exception):
    """A capability with this key already exists.

    The storage backstop for the lazy get-or-create (ADR-0013): both implementations
    raise it from `add`, mirroring the unique constraint on `capability.key`, so
    concurrent first-touches of a key can never create duplicate registry rows.
    """

    def __init__(self, key: str) -> None:
        super().__init__(f"capability already exists: {key}")


class CapabilityRepository(Protocol):
    """Persistence contract for the capability registry."""

    async def get_by_key(self, key: str) -> Capability | None:
        """Fetch a capability by its stable key."""
        ...

    async def add(self, capability: Capability) -> Capability:
        """Persist a newly created capability.

        Raises DuplicateCapabilityKeyError when the key is already registered.
        """
        ...

    async def list(self) -> list[Capability]:
        """Every registered capability, ordered by key."""
        ...


class InMemoryCapabilityRepository:
    """Dict-backed store for unit tests and DB-less development."""

    def __init__(self) -> None:
        self._by_key: dict[str, Capability] = {}

    async def get_by_key(self, key: str) -> Capability | None:
        return self._by_key.get(key)

    async def add(self, capability: Capability) -> Capability:
        # Mirror the unique constraint on capability.key so in-memory and Postgres
        # modes enforce the same invariant.
        if capability.key in self._by_key:
            raise DuplicateCapabilityKeyError(capability.key)
        # Column defaults only apply on DB flush; mirror them here.
        if capability.id is None:
            capability.id = uuid.uuid4()
        if capability.created_at is None:
            capability.created_at = datetime.now(UTC)
        if capability.available is None:
            capability.available = True
        self._by_key[capability.key] = capability
        return capability

    async def list(self) -> list[Capability]:
        return sorted(self._by_key.values(), key=lambda c: c.key)
