"""The caregiver push seam (ADR-0047 Phase B1) — capture, PHI-free shape, OFF-by-default.

B1 ships the seam only: an ``InMemoryPushSender`` that captures sends (tests inspect it)
and a NO-OP ``FcmPushSender`` stub wired behind ``caregiver_push_enabled`` (default
False). The ``PushMessage`` shape is PHI-free by construction — there is no field for a
patient name, value, or note text — which this file locks down.
"""

from __future__ import annotations

import dataclasses
import uuid

from app.services.push import FcmPushSender, InMemoryPushSender, PushMessage


def _message() -> PushMessage:
    return PushMessage(
        caregiver_user_id=uuid.uuid4(),
        alert_type="trend_shift",
        alert_id=uuid.uuid4(),
        title="A shift in the wellness trend",
        body="The weekly wellness trend has shifted.",
    )


async def test_in_memory_sender_captures_every_send() -> None:
    sender = InMemoryPushSender()
    assert sender.sent == []
    message = _message()
    await sender.send(message)
    assert sender.sent == [message]


async def test_fcm_stub_is_a_noop_in_b1() -> None:
    # The B2 seam: it accepts a message and does nothing (no network, no error).
    assert await FcmPushSender().send(_message()) is None


def test_push_message_is_phi_free_by_shape() -> None:
    # The dataclass carries ONLY identifiers + fixed template text — the structural
    # guarantee that a value/name/code can never ride a push payload.
    fields = {f.name for f in dataclasses.fields(PushMessage)}
    assert fields == {"caregiver_user_id", "alert_type", "alert_id", "title", "body"}
    # No field that could carry PHI (a patient name, a numeric value, note text, a code).
    for banned in ("patient_name", "display_name", "value", "value_num", "note", "code"):
        assert banned not in fields


def test_push_message_is_frozen() -> None:
    # Immutable: a captured payload can never be mutated to smuggle a value in later.
    message = _message()
    try:
        message.title = "changed"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("PushMessage must be frozen")
