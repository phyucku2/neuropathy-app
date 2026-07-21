"""Caregiver push seam (ADR-0047 Phase B1) — the B2 fan-out boundary, no real push yet.

A ``PushSender`` Protocol with an ``InMemoryPushSender`` (captures sends, used in tests)
and a NO-OP ``FcmPushSender`` stub wired behind ``settings.caregiver_push_enabled``
(DEFAULT OFF). B1 emits nothing to a device: this build establishes the seam and proves
the payload is PHI-free by contract. The real FCM HTTP v1 client + Firebase
service-account credential land in B2.

PHI-FREE BY CONTRACT: ``PushMessage`` carries only identifiers + fixed template text —
never a patient name, a value, a code label, or note text. The dataclass shape is the
enforcement (there is no field to leak a value into), mirroring the token-free
ConnectionOut / body-free EmrClinicalNote structural-absence idiom.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PushMessage:
    """A caregiver push notification — PHI-FREE by contract (ADR-0047 B1).

    Identifiers + fixed non-diagnostic template text ONLY. There is deliberately no
    field for a patient name, an observation value, a code display, or note text — the
    structural absence is the guarantee (proven by tests scanning the shape)."""

    caregiver_user_id: uuid.UUID
    alert_type: str  # a CaregiverAlertType value — a reference, never a value
    alert_id: uuid.UUID
    title: str  # a fixed non-diagnostic template constant (ALERT_TEMPLATES)
    body: str  # a fixed non-urgent template constant (ALERT_TEMPLATES)


class PushSender(Protocol):
    """Where a caregiver push goes when a new alert is persisted."""

    async def send(self, message: PushMessage) -> None: ...


class InMemoryPushSender:
    """List-backed sender for unit tests and DB-less development — captures every send
    so tests can assert the push seam fired with a PHI-free payload."""

    def __init__(self) -> None:
        self.sent: list[PushMessage] = []

    async def send(self, message: PushMessage) -> None:
        self.sent.append(message)


class FcmPushSender:
    """STUB — the B2 seam only (ADR-0047). The real FCM HTTP v1 client and the Firebase
    service-account credential land in B2; B1 leaves this a NO-OP, wired only when
    ``settings.caregiver_push_enabled`` is True (default False). Any real payload built
    here MUST stay PHI-free — the ``PushMessage`` shape enforces that contract."""

    async def send(self, message: PushMessage) -> None:  # no-op in B1
        return None
