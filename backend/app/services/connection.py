"""Connection-mode domain rules (ADR-0005).

Pure, DB-free predicates so the consent-gating invariant is locked by unit tests and
reusable anywhere a data-flow decision is made.
"""

from __future__ import annotations

from app.models.connection import ClinicConnection, ConnectionStatus


def may_transmit_to_clinic(connection: ClinicConnection) -> bool:
    """True only if this clinical connection permits sending patient data to the clinic.

    Data flows ONLY when the connection is active AND consent has been granted and not
    revoked — never on a clinician toggle alone (HIPAA; ADR-0003, ADR-0005).
    """
    return (
        connection.status is ConnectionStatus.active
        and connection.consent_granted_at is not None
        and connection.revoked_at is None
    )
