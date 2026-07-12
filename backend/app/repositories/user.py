"""User repository — interface + in-memory implementation (ADR-0010).

`UserRecord` is the storage-agnostic twin of `models.User` the auth service works
with; the Postgres implementation (repositories/postgres.py) maps it to the ORM row.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.models.user import UserRole


class DuplicateEmailError(Exception):
    """The email is already registered (unique-constraint violation)."""


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
        """Persist a new user atomically with its linked Patient record.

        Owns email uniqueness: raises DuplicateEmailError on a taken email (atomic in
        Postgres via the unique index — no check-then-insert race).
        """
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
        # Patient records created alongside patient users (parity with Postgres).
        self.patients: dict[uuid.UUID, str] = {}

    async def add(self, user: UserRecord) -> None:
        if user.email in self._by_email:
            raise DuplicateEmailError(user.email)
        self._by_email[user.email] = user
        self._by_id[user.id] = user
        if user.patient_id is not None:
            self.patients[user.patient_id] = user.display_name

    async def get_by_email(self, email: str) -> UserRecord | None:
        return self._by_email.get(email)

    async def get_by_id(self, user_id: uuid.UUID) -> UserRecord | None:
        return self._by_id.get(user_id)
