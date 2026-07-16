"""Add 'wearable' to the source_type enum for phone/watch mobility ingestion (ADR-0035).

Hand-written to match Base.metadata exactly (the integration suite verifies parity by
asserting autogenerate produces an empty diff against an upgraded database). The model
enum (app/models/observation.SourceType) now lists lab/adl/biomech/wearable; this
migration brings the database enum to the same set.

Postgres cannot run ALTER TYPE ... ADD VALUE inside a transaction block, so the value is
added in alembic's autocommit_block. IF NOT EXISTS makes a partial or repeated apply safe.

Downgrade is a deliberate no-op (as with 0003): Postgres has no safe DROP VALUE, and
removing 'wearable' would mean recreating source_type and rewriting every observation
row — data-loss risk on an append-only, research-grade store. An unused enum value is
harmless, so the value stays.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ADD VALUE cannot run inside a transaction; autocommit_block commits the surrounding
    # transaction and runs this on its own connection. IF NOT EXISTS keeps a re-run (or a
    # partially applied migration) from failing.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'wearable'")


def downgrade() -> None:
    # Intentional no-op (as with 0003 'biomech'): Postgres enums have no safe DROP VALUE;
    # removing the value would require recreating source_type and rewriting every
    # observation.source — data-loss risk on an append-only, research-grade store.
    pass
