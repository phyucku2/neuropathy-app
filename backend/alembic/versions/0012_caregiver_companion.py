"""Caregiver Companion Phase A (ADR-0047) — 'caregiver' role + invite/link tables.

Adds the 'caregiver' value to the existing user_role enum, then creates the
caregiver_invite table (patient-generated single-use codes, sha256 hex only — the
plaintext code is never stored) and the caregiver_link table (the patient↔caregiver
consent lifecycle mirroring clinic_connection, including the partial unique
uq_caregiver_link_live index: at most one live link per patient-caregiver pair).

The ALTER TYPE ... ADD VALUE runs in an autocommit block: Postgres refuses to USE a
just-added enum value inside the same transaction that added it, and alembic runs
migrations transactionally — committing the ADD VALUE first keeps any future step
(and the very next request after upgrade) free to write role='caregiver'. Nothing in
THIS migration inserts the value, so the isolation is precautionary but deliberate.

Downgrade drops the new tables and their two new enum types; the 'caregiver' enum
VALUE stays in user_role (Postgres cannot remove an enum value) — harmless, since no
row can carry it once the tables and code paths are gone.

Hand-written to match Base.metadata exactly (the integration suite verifies parity by
asserting autogenerate produces an empty diff against an upgraded database).

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Committed on its own (see the docstring): a value added inside the migration
    # transaction could not be used until that transaction ends.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'caregiver'")

    op.create_table(
        "caregiver_invite",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patient.id"]),
    )
    op.create_index("ix_caregiver_invite_code_hash", "caregiver_invite", ["code_hash"], unique=True)
    op.create_index(
        "ix_caregiver_invite_patient_id", "caregiver_invite", ["patient_id"], unique=False
    )

    op.create_table(
        "caregiver_link",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("caregiver_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.Enum("trends", "full", name="caregiver_scope"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "active", "revoked", name="caregiver_link_status"),
            nullable=False,
        ),
        # Reuses the existing `initiator` enum type (created in 0001) — do not re-create.
        sa.Column(
            "initiated_by", postgresql.ENUM(name="initiator", create_type=False), nullable=False
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patient.id"]),
        sa.ForeignKeyConstraint(["caregiver_user_id"], ["app_user.id"]),
    )
    op.create_index(
        "ix_caregiver_link_caregiver_user_id", "caregiver_link", ["caregiver_user_id"], unique=False
    )
    op.create_index("ix_caregiver_link_patient_id", "caregiver_link", ["patient_id"], unique=False)
    # One live (non-revoked) link per patient-caregiver PAIR — the storage backstop
    # for the claim flow's check-then-insert, mirroring uq_clinic_connection_live.
    op.create_index(
        "uq_caregiver_link_live",
        "caregiver_link",
        ["patient_id", "caregiver_user_id"],
        unique=True,
        postgresql_where=sa.text("status != 'revoked'"),
    )


def downgrade() -> None:
    op.drop_index("uq_caregiver_link_live", table_name="caregiver_link")
    op.drop_index("ix_caregiver_link_patient_id", table_name="caregiver_link")
    op.drop_index("ix_caregiver_link_caregiver_user_id", table_name="caregiver_link")
    op.drop_table("caregiver_link")
    op.drop_index("ix_caregiver_invite_patient_id", table_name="caregiver_invite")
    op.drop_index("ix_caregiver_invite_code_hash", table_name="caregiver_invite")
    op.drop_table("caregiver_invite")
    for enum_name in ("caregiver_scope", "caregiver_link_status"):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=False)
    # The 'caregiver' value remains in user_role (see the module docstring).
