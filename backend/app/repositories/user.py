"""User repository — interface + in-memory implementation (ADR-0010).

`UserRecord` is the storage-agnostic twin of `models.User` the auth service works
with; the Postgres implementation (repositories/postgres.py) maps it to the ORM row.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol

from app.models.patient import ConnectionMode
from app.models.user import UserRole


class DuplicateEmailError(Exception):
    """The email is already registered (unique-constraint violation)."""


class OpsAlreadyExistsError(Exception):
    """An ops account already exists when a first-ops bootstrap was attempted.

    Raised by `add_first_ops` when the count-then-insert is lost to a concurrent
    bootstrap: the single documented "first operator" invariant holds even under a
    race, and the loser is refused (ADR-0019).
    """


class OpsDeactivateOutcome(Enum):
    """The result of a guarded, atomic ops deactivation (ADR-0019)."""

    not_found = "not_found"  # unknown id or a non-ops account
    already_inactive = "already_inactive"  # idempotent no-op (carries the record)
    refused_last_active = "refused_last_active"  # would remove the last active operator
    deactivated = "deactivated"  # flipped active off (carries the updated record)


@dataclass(frozen=True)
class OpsDeactivateResult:
    outcome: OpsDeactivateOutcome
    # Present for already_inactive and deactivated; None for not_found/refused.
    record: UserRecord | None


@dataclass
class UserRecord:
    """Storage-agnostic twin of models.User."""

    id: uuid.UUID
    email: str
    password_hash: str
    display_name: str
    role: UserRole
    patient_id: uuid.UUID | None
    # Set for clinician users (ADR-0012); defaulted last so existing constructions
    # keep working unchanged.
    clinic_id: uuid.UUID | None = None
    # Per-account revocation (ADR-0019). Defaulted last for the same reason: an account
    # is active until explicitly deactivated (disabled_at then stamps when).
    active: bool = True
    disabled_at: datetime | None = None
    # When the account row was created (models.User Timestamps). Defaulted last and
    # populated by the store (server_default in Postgres, stamped on add in-memory), so
    # the data-export account profile (ADR-0031) can report it without a hand-rolled read.
    created_at: datetime | None = None


@dataclass
class PatientRecord:
    """Storage-agnostic twin of the non-secret fields of models.Patient.

    The Patient clinical record is created alongside its patient User (both stores'
    `add`), so the user repository — the single owner of that creation — is also where
    it is read back for the data export (ADR-0031). Carries only non-secret fields;
    the reserved `clinic_id` column (models.Patient — not maintained) is deliberately
    omitted so the export never reports a value nothing populates.
    """

    id: uuid.UUID
    display_name: str
    connection_mode: ConnectionMode
    created_at: datetime | None = None


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

    async def get_by_patient_id(self, patient_id: uuid.UUID) -> UserRecord | None:
        """Look up the patient user owning a Patient record (clinician panel display)."""
        ...

    async def get_patient(self, patient_id: uuid.UUID) -> PatientRecord | None:
        """Read the linked Patient clinical record's non-secret fields (ADR-0031 data
        export). The mirror of `add`, which creates the Patient row with the user; None
        when no such patient exists."""
        ...

    async def count_with_role(self, role: UserRole, *, active_only: bool = False) -> int:
        """How many accounts hold `role`. `active_only` counts only active ones.

        The ops-auth surface (ADR-0019) uses this twice: `count_with_role(ops) == 0`
        decides whether the first-ops bootstrap gate is still open, and
        `count_with_role(ops, active_only=True)` guards against deactivating the last
        active operator (which — with the bootstrap closed once any ops exists — would
        lock the provisioning surface out entirely).
        """
        ...

    async def set_active(
        self, user_id: uuid.UUID, *, active: bool, disabled_at: datetime | None
    ) -> UserRecord | None:
        """Flip an account's active flag (ADR-0019 revocation), stamping disabled_at.
        Returns the updated record, or None when no such user exists."""
        ...

    async def add_first_ops(self, user: UserRecord) -> None:
        """Insert the FIRST ops account, atomically guarded against a concurrent
        bootstrap (ADR-0019).

        With zero ops rows there is nothing to row-lock, so Postgres serializes the
        count-then-insert on a transaction-scoped advisory lock; the loser re-reads a
        now-nonzero ops count and raises OpsAlreadyExistsError. Also raises
        DuplicateEmailError like `add` when the email is taken. Callers use this only on
        the first-ops path; steady-state creation uses `add`.
        """
        ...

    async def deactivate_ops_guarded(
        self, user_id: uuid.UUID, *, disabled_at: datetime
    ) -> OpsDeactivateResult:
        """Count active ops and flip the target off in ONE atomic step (ADR-0019).

        Closes the last-active-ops TOCTOU: reading the count and then deactivating in
        separate steps let two concurrent deactivations both pass the >1 guard and drive
        active ops to zero — a permanent provisioning lockout. Postgres locks the
        active-ops set FOR UPDATE so concurrent deactivations serialize; the second
        waiter re-reads the just-committed flip, sees the reduced count, and is refused.
        The in-memory twin never awaits between the count and the flip, so the single
        event loop gives it the same atomicity.
        """
        ...

    async def delete_with_patient(self, *, user_id: uuid.UUID, patient_id: uuid.UUID) -> None:
        """Destroy the auth identity AND its linked Patient clinical record — the
        mirror of `add`, which creates both together (ADR-0027 account deletion).

        Callers own the FK order: every table referencing the patient row must already
        be empty (or, for audit_event, detach via ON DELETE SET NULL — migration
        0006). The patient row is the LAST thing account deletion destroys.
        """
        ...

    async def delete_user(self, user_id: uuid.UUID) -> None:
        """Destroy a PATIENT-LESS auth identity (a caregiver account, ADR-0047).

        Callers own the FK order: every table referencing the user row (caregiver
        links) must already be empty. Patient accounts go through
        `delete_with_patient` instead — this never touches a Patient record.
        """
        ...


class InMemoryUserRepository:
    """Dict-backed store for unit tests and DB-less development."""

    def __init__(self) -> None:
        self._by_email: dict[str, UserRecord] = {}
        self._by_id: dict[uuid.UUID, UserRecord] = {}
        # Patient records created alongside patient users (parity with Postgres).
        self.patients: dict[uuid.UUID, PatientRecord] = {}

    async def add(self, user: UserRecord) -> None:
        if user.email in self._by_email:
            raise DuplicateEmailError(user.email)
        # Server default (created_at) only applies on DB flush; mirror it here so the
        # in-memory account profile reports a timestamp too (ADR-0031).
        if user.created_at is None:
            user.created_at = datetime.now(UTC)
        self._by_email[user.email] = user
        self._by_id[user.id] = user
        if user.patient_id is not None:
            # Registration always creates a self_connected patient (models.Patient
            # default) — the Postgres `add` constructs it the same way.
            self.patients[user.patient_id] = PatientRecord(
                id=user.patient_id,
                display_name=user.display_name,
                connection_mode=ConnectionMode.self_connected,
                created_at=user.created_at,
            )

    async def get_by_email(self, email: str) -> UserRecord | None:
        return self._by_email.get(email)

    async def get_by_id(self, user_id: uuid.UUID) -> UserRecord | None:
        return self._by_id.get(user_id)

    async def get_by_patient_id(self, patient_id: uuid.UUID) -> UserRecord | None:
        return next((u for u in self._by_id.values() if u.patient_id == patient_id), None)

    async def get_patient(self, patient_id: uuid.UUID) -> PatientRecord | None:
        return self.patients.get(patient_id)

    async def count_with_role(self, role: UserRole, *, active_only: bool = False) -> int:
        return sum(
            1 for u in self._by_id.values() if u.role is role and (u.active or not active_only)
        )

    async def set_active(
        self, user_id: uuid.UUID, *, active: bool, disabled_at: datetime | None
    ) -> UserRecord | None:
        user = self._by_id.get(user_id)
        if user is None:
            return None
        # Stored by reference (also in _by_email), so mutating in place updates both.
        user.active = active
        user.disabled_at = disabled_at
        return user

    async def add_first_ops(self, user: UserRecord) -> None:
        # Single-threaded event loop: the count check and the insert run with no await
        # in between, so no concurrent bootstrap interleaves (the Postgres twin gets the
        # same guarantee from an advisory lock).
        if any(u.role is UserRole.ops for u in self._by_id.values()):
            raise OpsAlreadyExistsError(str(user.id))
        await self.add(user)

    async def deactivate_ops_guarded(
        self, user_id: uuid.UUID, *, disabled_at: datetime
    ) -> OpsDeactivateResult:
        # No await between the count and the flip -> atomic in the single event loop.
        user = self._by_id.get(user_id)
        if user is None or user.role is not UserRole.ops:
            return OpsDeactivateResult(OpsDeactivateOutcome.not_found, None)
        if not user.active:
            return OpsDeactivateResult(OpsDeactivateOutcome.already_inactive, user)
        active = sum(1 for u in self._by_id.values() if u.role is UserRole.ops and u.active)
        if active <= 1:
            return OpsDeactivateResult(OpsDeactivateOutcome.refused_last_active, None)
        user.active = False
        user.disabled_at = disabled_at
        return OpsDeactivateResult(OpsDeactivateOutcome.deactivated, user)

    async def delete_with_patient(self, *, user_id: uuid.UUID, patient_id: uuid.UUID) -> None:
        user = self._by_id.pop(user_id, None)
        if user is not None:
            self._by_email.pop(user.email, None)
        self.patients.pop(patient_id, None)

    async def delete_user(self, user_id: uuid.UUID) -> None:
        user = self._by_id.pop(user_id, None)
        if user is not None:
            self._by_email.pop(user.email, None)
