"""Add the food-log enum values: source_type 'food' + data_origin 'patient_estimated' (ADR-0042).

Hand-written to match Base.metadata exactly (the integration suite verifies parity by
asserting autogenerate produces an empty diff against an upgraded database). The model enums
(app/models/observation.SourceType / DataOrigin) now list 'food' and 'patient_estimated';
this migration brings the database enums to the same set so patient food logs can be stored
as append-only Observations (source=food, origin=patient_estimated) — a ranged self-tracking
estimate, excluded from the NSI (its source is deliberately absent from TRAJECTORY_SOURCES).

Postgres cannot run ALTER TYPE ... ADD VALUE inside a transaction block, so the values are
added in alembic's autocommit_block. IF NOT EXISTS makes a partial or repeated apply safe.

Downgrade is a deliberate no-op (as with 0003/0007): Postgres has no safe DROP VALUE, and
removing a value would mean recreating the enum and rewriting every observation row —
data-loss risk on an append-only, research-grade store. An unused enum value is harmless.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ADD VALUE cannot run inside a transaction; autocommit_block commits the surrounding
    # transaction and runs these on their own connection. IF NOT EXISTS keeps a re-run (or a
    # partially applied migration) from failing.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'food'")
        op.execute("ALTER TYPE data_origin ADD VALUE IF NOT EXISTS 'patient_estimated'")


def downgrade() -> None:
    # Intentional no-op (as with 0003 'biomech' / 0007 'wearable'): Postgres enums have no
    # safe DROP VALUE; removing a value would require recreating the enum and rewriting every
    # observation row — data-loss risk on an append-only, research-grade store.
    pass
