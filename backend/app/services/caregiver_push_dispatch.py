"""Post-commit caregiver-push fan-out (ADR-0047 Phase B2).

The alert engine ACCUMULATES the ``PushMessage``s for newly-inserted alerts on a feed
read (services/caregiver_alert.py); the route schedules this fan-out as a Starlette
``BackgroundTask`` — which runs AFTER the response is sent, i.e. AFTER the request
transaction commits (app/db/session.py yields inside ``session.begin()``). So a
rolled-back feed read never pushes, and the real network send never sits inside the
request transaction (mirrors the narrator seam).

The fan-out opens its OWN short-lived session (the request's is already closed) to read
each caregiver's device tokens and prune any the FCM sender reports dead
(``UNREGISTERED`` / 404 / token ``INVALID_ARGUMENT``). Every transient error is
swallowed: a background push failure must never surface anywhere.
"""

from __future__ import annotations

import logging

from app.repositories.caregiver_push_token import CaregiverPushTokenRepository
from app.services.push import PushMessage, TokenPushSender, TokenSendOutcome

_log = logging.getLogger(__name__)


async def fan_out_caregiver_push(
    *,
    messages: list[PushMessage],
    tokens: CaregiverPushTokenRepository,
    sender: TokenPushSender,
) -> None:
    """Send each message to every one of the caregiver's device tokens, pruning dead
    ones. Never raises — a background push must not break anything (all failures are
    swallowed and logged PHI-free)."""
    for message in messages:
        try:
            rows = await tokens.list_for_caregiver(message.caregiver_user_id)
        except Exception:
            _log.warning("caregiver push fan-out: token lookup failed (swallowed)")
            continue
        for row in rows:
            try:
                outcome = await sender.send_to_token(message, row.token)
            except Exception:
                # Defense in depth: the sender already swallows, but never trust a
                # background callee to break the loop for the remaining tokens.
                _log.warning("caregiver push fan-out: send failed (swallowed)")
                continue
            if outcome is TokenSendOutcome.unregistered:
                try:
                    await tokens.delete_by_token(row.token)
                except Exception:
                    _log.warning("caregiver push fan-out: dead-token prune failed (swallowed)")
