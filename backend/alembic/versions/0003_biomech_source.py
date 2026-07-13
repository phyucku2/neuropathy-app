"""Add 'biomech' to the source_type enum for the BioMech PDF ingest module (ADR-0014).

Hand-written to match Base.metadata exactly (the integration suite verifies parity by
asserting autogenerate produces an empty diff against an upgraded database). The model
enum (app/models/observation.SourceType) now lists lab/adl/biomech; this migration
brings the database enum to the same set.

Postgres cannot run ALTER TYPE ... ADD VALUE inside a transaction block, so the value
is added in alembic's autocommit_block (it commits the surrounding transaction and
runs the statement on its own connection). IF NOT EXISTS makes a partial or repeated
apply safe.

Downgrade is a deliberate no-op: Postgres has no DROP VALUE, and removing 'biomech'
would mean recreating source_type without it and rewriting every observation row's
source column — data-loss risk on a research-grade, append-only store (ADR-0014).
An unused enum value is harmless, so downgrade leaves it in place.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ADD VALUE cannot run inside a transaction; autocommit_block commits the
    # surrounding transaction and runs this on its own connection. IF NOT EXISTS keeps
    # a re-run (or a partially applied migration) from failing.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'biomech'")


def downgrade() -> None:
    # Intentional no-op (ADR-0014): Postgres enums have no safe DROP VALUE. Removing
    # 'biomech' would require recreating source_type without it and rewriting every
    # observation.source value — data-loss risk on an append-only, research-grade
    # store. An unused enum value is harmless, so the value stays.
    pass
