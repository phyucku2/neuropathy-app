"""Add 'medication' and 'event' to source_type + the source-scoped read index (ADR-0045 P2).

Patient-entered medications/supplements and between-visit events/notes ride the existing
`observation` model (no new tables): two new SourceType members and a
(patient_id, source, effective_at) index that keeps the medication current-state fold's
full-history, source-scoped read in budget.

Hand-written to match Base.metadata exactly (the integration suite verifies parity by
asserting autogenerate produces an empty diff against an upgraded database). The model
enum (app/models/observation.SourceType) now lists lab/adl/biomech/wearable/medication/
event; this migration brings the database enum to the same set.

Postgres cannot run ALTER TYPE ... ADD VALUE inside a transaction block, so each value is
added in alembic's autocommit_block (mirrors 0007). IF NOT EXISTS makes a partial or
repeated apply safe.

Downgrade: a deliberate no-op for the enum values (as with 0003/0007 — Postgres has no
safe DROP VALUE on an append-only, research-grade store), and drops the index.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ADD VALUE cannot run inside a transaction; autocommit_block commits the surrounding
    # transaction and runs each on its own connection. IF NOT EXISTS keeps a re-run (or a
    # partially applied migration) from failing.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'medication'")
        op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'event'")
    # The source-scoped full-history medication fold read (list_for_patient(source=...))
    # is backed by this index so it never scans a patient's whole record.
    op.create_index(
        "ix_observation_patient_source_time",
        "observation",
        ["patient_id", "source", "effective_at"],
    )


def downgrade() -> None:
    # Drop only the index. Removing the enum values would require recreating source_type
    # and rewriting every observation.source — data-loss risk on an append-only,
    # research-grade store (as with 0003/0007), so the values stay.
    op.drop_index("ix_observation_patient_source_time", table_name="observation")
