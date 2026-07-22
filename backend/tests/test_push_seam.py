"""The caregiver push seam (ADR-0047) — capture + the PHI-free ``PushMessage`` shape.

The in-app seam pieces that survive into B2: an ``InMemoryPushSender`` that captures
sends and the ``PushMessage`` shape, which is PHI-free by construction — there is no
field for a patient name, value, or note text. (The real FCM sender + fan-out are
covered in tests/test_caregiver_push.py.)
"""

from __future__ import annotations

import dataclasses
import uuid

from app.services.push import InMemoryPushSender, PushMessage


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
