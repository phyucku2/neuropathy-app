"""Tests for the consent-gating rule (ADR-0005): data flows to a clinic only on
active, consented, non-revoked connections — never on a clinician toggle alone.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.connection import ClinicConnection, ConnectionStatus, Initiator
from app.services.connection import may_transmit_to_clinic


def _conn(
    status: ConnectionStatus,
    consent: datetime | None,
    revoked: datetime | None = None,
) -> ClinicConnection:
    return ClinicConnection(
        status=status,
        initiated_by=Initiator.clinic,
        consent_granted_at=consent,
        revoked_at=revoked,
    )


def test_active_and_consented_may_transmit() -> None:
    assert may_transmit_to_clinic(_conn(ConnectionStatus.active, datetime.now(UTC))) is True


def test_pending_without_consent_may_not_transmit() -> None:
    assert may_transmit_to_clinic(_conn(ConnectionStatus.pending, None)) is False


def test_active_but_no_consent_may_not_transmit() -> None:
    # A clinician activating the connection is NOT enough — consent must exist.
    assert may_transmit_to_clinic(_conn(ConnectionStatus.active, None)) is False


def test_revoked_may_not_transmit_even_if_previously_consented() -> None:
    now = datetime.now(UTC)
    assert may_transmit_to_clinic(_conn(ConnectionStatus.revoked, now, revoked=now)) is False
