"""Caregiver invite/link repositories — interfaces + in-memory implementations
(ADR-0047), mirroring repositories/clinic_connection.py.

Both work directly with `models.CaregiverInvite` / `models.CaregiverLink` — the rows
`_may_caregiver_read` (app/services/caregiver.py) judges, so the consent gate is
applied to exactly what storage holds, never a diverging copy.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from app.models.caregiver import CaregiverInvite, CaregiverLink, CaregiverLinkStatus


class DuplicateLiveCaregiverLinkError(Exception):
    """A non-revoked link already joins this patient and caregiver.

    The storage backstop for the claim flow's check-then-insert (ADR-0047): both
    implementations raise it from `add`, mirroring the `uq_caregiver_link_live`
    partial unique index, so concurrent claims can never create duplicates.
    """

    def __init__(self, patient_id: uuid.UUID, caregiver_user_id: uuid.UUID) -> None:
        super().__init__(
            f"live caregiver link already exists: patient {patient_id}, "
            f"caregiver {caregiver_user_id}"
        )


class CaregiverInviteRepository(Protocol):
    """Persistence contract for patient-generated caregiver invite codes."""

    async def add(self, invite: CaregiverInvite) -> CaregiverInvite:
        """Persist a newly created invite (code_hash only — never the code)."""
        ...

    async def get(self, invite_id: uuid.UUID) -> CaregiverInvite | None:
        """Fetch an invite by id."""
        ...

    async def get_by_code_hash(self, code_hash: str) -> CaregiverInvite | None:
        """Fetch an invite by its sha256 hex — the claim flow's lookup."""
        ...

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[CaregiverInvite]:
        """All of one patient's invites (every state), oldest first."""
        ...

    async def consume(self, invite_id: uuid.UUID, *, now: datetime) -> bool:
        """Atomically mark an open invite consumed; False when it was already
        consumed or cancelled (a lost claim race, or a dead code). Single-use is
        enforced HERE, not by check-then-write: Postgres uses one conditional
        UPDATE, the in-memory twin never awaits between check and set."""
        ...

    async def update(self, invite: CaregiverInvite) -> None:
        """Persist the current state of an existing invite (cancellation)."""
        ...

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        """Destroy every invite row for one patient (ADR-0027 account deletion)."""
        ...


class CaregiverLinkRepository(Protocol):
    """Persistence contract for patient-caregiver consent links."""

    async def add(self, link: CaregiverLink) -> CaregiverLink:
        """Persist a newly created link.

        Raises DuplicateLiveCaregiverLinkError when a non-revoked link for the same
        (patient_id, caregiver_user_id) already exists.
        """
        ...

    async def get(self, link_id: uuid.UUID) -> CaregiverLink | None:
        """Fetch a link by id."""
        ...

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[CaregiverLink]:
        """All of one patient's links (every status), oldest first."""
        ...

    async def list_for_caregiver(self, caregiver_user_id: uuid.UUID) -> list[CaregiverLink]:
        """All of one caregiver's links (every status), oldest first.

        Storage-level narrowing only — callers MUST still apply
        `_may_caregiver_read` before any data flows (acceptance, not existence,
        gates reads — ADR-0047 double opt-in)."""
        ...

    async def update(self, link: CaregiverLink) -> None:
        """Persist the current state of an existing link."""
        ...

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        """Destroy every link row for one patient (ADR-0027 account deletion).
        Deleting the rows also ends any live consent: with no link left,
        `_may_caregiver_read` can never pass for this patient again."""
        ...

    async def delete_for_caregiver(self, caregiver_user_id: uuid.UUID) -> None:
        """Destroy every link row for one caregiver account (its deletion)."""
        ...


class InMemoryCaregiverInviteRepository:
    """Dict-backed store for unit tests and DB-less development."""

    def __init__(self) -> None:
        self._invites: dict[uuid.UUID, CaregiverInvite] = {}

    async def add(self, invite: CaregiverInvite) -> CaregiverInvite:
        # Column defaults (id, created_at) only apply on DB flush; mirror them here.
        if invite.id is None:
            invite.id = uuid.uuid4()
        if invite.created_at is None:
            invite.created_at = datetime.now(UTC)
        self._invites[invite.id] = invite
        return invite

    async def get(self, invite_id: uuid.UUID) -> CaregiverInvite | None:
        return self._invites.get(invite_id)

    async def get_by_code_hash(self, code_hash: str) -> CaregiverInvite | None:
        return next((i for i in self._invites.values() if i.code_hash == code_hash), None)

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[CaregiverInvite]:
        rows = [i for i in self._invites.values() if i.patient_id == patient_id]
        return sorted(rows, key=lambda i: i.created_at)

    async def consume(self, invite_id: uuid.UUID, *, now: datetime) -> bool:
        # No await between the check and the set -> atomic in the single event loop
        # (the Postgres twin gets the same guarantee from one conditional UPDATE).
        invite = self._invites.get(invite_id)
        if invite is None or invite.consumed_at is not None or invite.cancelled_at is not None:
            return False
        invite.consumed_at = now
        return True

    async def update(self, invite: CaregiverInvite) -> None:
        self._invites[invite.id] = invite

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        self._invites = {iid: i for iid, i in self._invites.items() if i.patient_id != patient_id}


class InMemoryCaregiverLinkRepository:
    """Dict-backed store for unit tests and DB-less development."""

    def __init__(self) -> None:
        self._links: dict[uuid.UUID, CaregiverLink] = {}

    async def add(self, link: CaregiverLink) -> CaregiverLink:
        # Mirror the uq_caregiver_link_live partial unique index so in-memory and
        # Postgres modes enforce the same invariant.
        for existing in self._links.values():
            if (
                existing.patient_id == link.patient_id
                and existing.caregiver_user_id == link.caregiver_user_id
                and existing.status is not CaregiverLinkStatus.revoked
            ):
                raise DuplicateLiveCaregiverLinkError(link.patient_id, link.caregiver_user_id)
        # Column defaults (id, created_at) only apply on DB flush; mirror them here.
        if link.id is None:
            link.id = uuid.uuid4()
        if link.created_at is None:
            link.created_at = datetime.now(UTC)
        self._links[link.id] = link
        return link

    async def get(self, link_id: uuid.UUID) -> CaregiverLink | None:
        return self._links.get(link_id)

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[CaregiverLink]:
        rows = [c for c in self._links.values() if c.patient_id == patient_id]
        return sorted(rows, key=lambda c: c.created_at)

    async def list_for_caregiver(self, caregiver_user_id: uuid.UUID) -> list[CaregiverLink]:
        rows = [c for c in self._links.values() if c.caregiver_user_id == caregiver_user_id]
        return sorted(rows, key=lambda c: c.created_at)

    async def update(self, link: CaregiverLink) -> None:
        self._links[link.id] = link

    async def delete_for_patient(self, patient_id: uuid.UUID) -> None:
        self._links = {lid: c for lid, c in self._links.items() if c.patient_id != patient_id}

    async def delete_for_caregiver(self, caregiver_user_id: uuid.UUID) -> None:
        self._links = {
            lid: c for lid, c in self._links.items() if c.caregiver_user_id != caregiver_user_id
        }
