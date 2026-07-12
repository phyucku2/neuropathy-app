"""User repository — interface + in-memory implementation (ADR-0010).

`UserRecord` is the storage-agnostic twin of `models.User` the auth service works
with; the Postgres implementation (repositories/postgres.py) maps it to the ORM row.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.models.user import UserRole


@dataclass
class UserRecord:
    """Storage-agnostic twin of models.User."""

    id: uuid.UUID
    email: str
    password_hash: str
    display_name: str
    role: UserRole
    patient_id: uuid.UUID | None


class UserRepository(Protocol):
    """Persistence contract for authentication identities."""

    async def add(self, user: UserRecord) -> None:
        """Persist a new user. The caller has already checked email uniqueness."""
        ...

    async def get_by_email(self, email: str) -> UserRecord | None:
        """Look up a user by normalized (lowercased) email."""
        ...

    async def get_by_id(self, user_id: uuid.UUID) -> UserRecord | None:
        """Look up a user by id."""
        ...


class InMemoryUserRepository:
    """Dict-backed store for unit tests and DB-less development."""

    def __init__(self) -> None:
        self._by_email: dict[str, UserRecord] = {}
        self._by_id: dict[uuid.UUID, UserRecord] = {}

    async def add(self, user: UserRecord) -> None:
        self._by_email[user.email] = user
        self._by_id[user.id] = user

    async def get_by_email(self, email: str) -> UserRecord | None:
        return self._by_email.get(email)

    async def get_by_id(self, user_id: uuid.UUID) -> UserRecord | None:
        return self._by_id.get(user_id)
