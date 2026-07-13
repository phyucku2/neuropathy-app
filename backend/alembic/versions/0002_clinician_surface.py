"""Clinician surface — clinic table + real clinic references (ADR-0012).

Hand-written to match Base.metadata exactly (the integration suite verifies parity by
asserting autogenerate produces an empty diff against an upgraded database).

Creates the clinic table, links clinician users to their clinic
(app_user.clinic_id), and turns clinic_connection.clinic_id from a bare UUID into a
real foreign key. Pre-launch: no rows exist yet, so the new constraint needs no
backfill.

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

    op.create_foreign_key(
        "fk_clinic_connection_clinic_id_clinic",
        "clinic_connection",
        "clinic",
        ["clinic_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_clinic_connection_clinic_id_clinic", "clinic_connection", type_="foreignkey"
    )
    op.drop_constraint("fk_app_user_clinic_id_clinic", "app_user", type_="foreignkey")
    op.drop_column("app_user", "clinic_id")
    op.drop_table("clinic")
