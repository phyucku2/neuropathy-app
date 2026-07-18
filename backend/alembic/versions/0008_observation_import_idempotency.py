"""Make import idempotency a DB-level invariant on observation (sweep #3).

Every import-keyed ingest path (labs via EMR pull or patient upload, biomech PDF metrics,
wearable/CGM samples) deduped with a read-then-write: probe `existing_import_keys`, then
insert the rows not already on file. That check-then-insert cannot hold under two
concurrent imports of the same source record — both probes see "absent", both insert — so
the same lab could land twice in the analyzable dataset. This migration replaces the
non-unique (patient_id, import_key) index with a PARTIAL UNIQUE index so the duplicate is
impossible in storage; the repository's `add_if_absent` turns the resulting conflict into a
graceful skip instead of a 500.

WHERE import_key IS NOT NULL scopes uniqueness to import-keyed rows only: ADL/symptom
check-ins carry a NULL import_key and are deduped by supersession (revises_id), so they are
untouched, and NULLs never collide. The partial unique index still serves the batch
existence probe (patient_id + import_key IN (...) implies NOT NULL), so it fully supersedes
the former non-unique ix_observation_patient_import_key — no redundant index is kept.

Hand-written to match Base.metadata exactly (the integration suite asserts autogenerate
produces an empty diff against an upgraded database).

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # De-dupe before adding the unique index (as 0002 did for clinic_connection): if any
    # duplicate import-keyed rows already slipped in through the pre-invariant race, keep
    # exactly the earliest per (patient_id, import_key) — deterministic tie-break on id —
    # and delete the rest, or CREATE UNIQUE INDEX would fail. Import-keyed rows are never
    # supersession targets (revises_id chains use NULL-import_key ADL/symptom rows), so
    # this delete cannot orphan a revises_id reference.
    op.execute(
        "DELETE FROM observation c "
        "WHERE c.import_key IS NOT NULL "
        "  AND EXISTS ("
        "    SELECT 1 FROM observation older "
        "    WHERE older.patient_id = c.patient_id "
        "      AND older.import_key = c.import_key "
        "      AND (older.created_at < c.created_at "
        "           OR (older.created_at = c.created_at AND older.id < c.id))"
        "  )"
    )
    # The unique partial index subsumes the batch existence probe the non-unique index
    # served, so replace rather than add: drop the old, create the new.
    op.drop_index("ix_observation_patient_import_key", table_name="observation")
    op.create_index(
        "uq_observation_patient_import_key",
        "observation",
        ["patient_id", "import_key"],
        unique=True,
        postgresql_where=sa.text("import_key IS NOT NULL"),
    )


def downgrade() -> None:
    # Reverse exactly: restore the non-unique index and drop the unique one. Safe — dropping
    # a uniqueness constraint never conflicts with existing data.
    op.drop_index("uq_observation_patient_import_key", table_name="observation")
    op.create_index(
        "ix_observation_patient_import_key",
        "observation",
        ["patient_id", "import_key"],
        unique=False,
    )
