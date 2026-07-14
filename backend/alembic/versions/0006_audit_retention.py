"""Audit retention across account deletion — audit_event.patient_id ON DELETE SET NULL
(ADR-0027).

Hand-written to match Base.metadata exactly (the integration suite verifies parity by
asserting autogenerate produces an empty diff against an upgraded database).

Account deletion (DELETE /auth/me) destroys the patient row LAST, in the same
transaction that already wrote its one PHI-free 'delete_account' audit event. Audit
events are RETAINED under regulatory retention — they hold references and counts,
never PHI values (audit model contract) — so the plain FK from migration 0001 would
either block the patient delete or force the history to be destroyed with it. Neither
is right: the FK becomes ON DELETE SET NULL, so a deleted patient's audit history
survives as anonymous events (patient_id NULL), including the deletion event itself.

Downgrade restores the plain FK from 0001. That is always safe — patient_id is
nullable and every remaining value still references a live patient row — and forfeits
only the automatic anonymize-on-delete behavior, so unlike 0002 there is nothing to
refuse over.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The default name Postgres gave the unnamed ForeignKeyConstraint in migration 0001.
_FK_NAME = "audit_event_patient_id_fkey"


def upgrade() -> None:
    op.drop_constraint(_FK_NAME, "audit_event", type_="foreignkey")
    op.create_foreign_key(
        _FK_NAME,
        "audit_event",
        "patient",
        ["patient_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(_FK_NAME, "audit_event", type_="foreignkey")
    op.create_foreign_key(
        _FK_NAME,
        "audit_event",
        "patient",
        ["patient_id"],
        ["id"],
    )
