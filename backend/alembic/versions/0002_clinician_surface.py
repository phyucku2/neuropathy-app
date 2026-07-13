"""Clinician surface — clinic table + real clinic references (ADR-0012).

Hand-written to match Base.metadata exactly (the integration suite verifies parity by
asserting autogenerate produces an empty diff against an upgraded database).

Creates the clinic table, links clinician users to their clinic
(app_user.clinic_id), turns clinic_connection.clinic_id from a bare UUID into a
real foreign key, and adds the partial unique index that allows at most one live
(non-revoked) connection per patient-clinic pair. Any clinic_id values already
present in clinic_connection are backfilled as placeholder clinic rows before the
constraint lands, so populated dev/staging databases upgrade cleanly; duplicate live
connections are revoked (keeping the oldest) before the unique index is created.

Downgrade refuses while clinic_connection rows exist: dropping the clinic table
under them would orphan consent-bearing records AND permanently block re-upgrading.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinic",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.add_column("app_user", sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_app_user_clinic_id_clinic", "app_user", "clinic", ["clinic_id"], ["id"]
    )

    # Backfill: clinic_connection.clinic_id predates the clinic table (0001 stored a
    # bare UUID), so any populated database would fail the new FK against an empty
    # clinic table. Placeholder rows keep referential integrity; operators rename them.
    op.execute(
        "INSERT INTO clinic (id, name) "
        "SELECT DISTINCT clinic_id, 'Backfilled by migration 0002 — rename me' "
        "FROM clinic_connection "
        "ON CONFLICT (id) DO NOTHING"
    )
    op.create_foreign_key(
        "fk_clinic_connection_clinic_id_clinic",
        "clinic_connection",
        "clinic",
        ["clinic_id"],
        ["id"],
    )

    # One live connection per patient-clinic pair (ADR-0012). Pre-existing duplicates
    # (possible under 0001, which had no constraint) are revoked keeping the oldest,
    # so the unique index always builds.
    op.execute(
        "UPDATE clinic_connection c SET status = 'revoked', revoked_at = now() "
        "WHERE c.status != 'revoked' AND EXISTS ("
        "  SELECT 1 FROM clinic_connection older"
        "  WHERE older.patient_id = c.patient_id AND older.clinic_id = c.clinic_id"
        "    AND older.status != 'revoked' AND older.created_at < c.created_at"
        ")"
    )
    op.create_index(
        "uq_clinic_connection_live",
        "clinic_connection",
        ["patient_id", "clinic_id"],
        unique=True,
        postgresql_where=sa.text("status != 'revoked'"),
    )


def downgrade() -> None:
    # Refuse rather than orphan: dropping clinic under existing clinic_connection rows
    # silently deletes clinics AND leaves dangling clinic_id values that make a later
    # `upgrade head` fail its FK forever (consent-bearing rows need deliberate handling).
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM clinic_connection LIMIT 1")).first() is not None:
        raise RuntimeError(
            "clinic_connection rows exist; downgrading 0002 would orphan consent "
            "records and permanently break re-upgrading. Resolve (archive or delete) "
            "the connections first."
        )
    op.drop_index("uq_clinic_connection_live", table_name="clinic_connection")
    op.drop_constraint(
        "fk_clinic_connection_clinic_id_clinic", "clinic_connection", type_="foreignkey"
    )
    op.drop_constraint("fk_app_user_clinic_id_clinic", "app_user", type_="foreignkey")
    op.drop_column("app_user", "clinic_id")
    op.drop_table("clinic")
