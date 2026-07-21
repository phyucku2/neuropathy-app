"""Caregiver Companion Phase B1 (ADR-0047) — compute-on-read alert + preference tables.

Adds the append-only ``caregiver_alert`` fact and the per-patient/per-type
``caregiver_alert_preference`` opt-in (DEFAULT OFF). Both carry the brand-new
``caregiver_alert_type`` enum: SQLAlchemy creates the type with the FIRST table, so
the second table's column references it with ``create_type=False`` (mirroring how
0012 reuses the ``initiator`` enum) — a second CREATE TYPE would fail.

``uq_caregiver_alert_link_type_dedupe`` is the once-only-per-logical-event backstop:
``add_if_absent`` absorbs its conflict exactly like ``uq_emr_note_patient_import_key``.
``dedupe_key`` is NOT NULL for every alert type, so a plain composite UNIQUE (no
partial WHERE) is the faithful analog of the observation partial-unique import index.
``caregiver_alert_preference`` gets ``uq_caregiver_alert_preference_patient_type`` to
enable the insert-first upsert (mirrors ``uq_patient_capability``).

Downgrade drops the indexes + both tables, then the new enum type.

Hand-written to match Base.metadata exactly (the integration suite verifies parity by
asserting autogenerate produces an empty diff against an upgraded database).

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "caregiver_alert",
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
        sa.Column("caregiver_link_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "alert_type",
            # The FIRST table creates the brand-new enum type; the preference table
            # below references it with create_type=False.
            sa.Enum(
                "missed_checkin",
                "med_change",
                "trend_shift",
                "new_chart_note",
                name="caregiver_alert_type",
            ),
            nullable=False,
        ),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patient.id"]),
        sa.ForeignKeyConstraint(["caregiver_link_id"], ["caregiver_link.id"]),
    )
    op.create_index(
        "ix_caregiver_alert_caregiver_link_id",
        "caregiver_alert",
        ["caregiver_link_id"],
        unique=False,
    )
    op.create_index(
        "ix_caregiver_alert_patient_id", "caregiver_alert", ["patient_id"], unique=False
    )
    # The once-only-per-logical-event backstop (dedupe_key NOT NULL for every type, so a
    # plain composite UNIQUE — the faithful analog of the observation partial-unique).
    op.create_index(
        "uq_caregiver_alert_link_type_dedupe",
        "caregiver_alert",
        ["caregiver_link_id", "alert_type", "dedupe_key"],
        unique=True,
    )

    op.create_table(
        "caregiver_alert_preference",
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
        sa.Column(
            "alert_type",
            # Reuse the enum type created with caregiver_alert above — do NOT re-create it.
            postgresql.ENUM(name="caregiver_alert_type", create_type=False),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patient.id"]),
    )
    op.create_index(
        "ix_caregiver_alert_preference_patient_id",
        "caregiver_alert_preference",
        ["patient_id"],
        unique=False,
    )
    op.create_index(
        "uq_caregiver_alert_preference_patient_type",
        "caregiver_alert_preference",
        ["patient_id", "alert_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_caregiver_alert_preference_patient_type", table_name="caregiver_alert_preference"
    )
    op.drop_index(
        "ix_caregiver_alert_preference_patient_id", table_name="caregiver_alert_preference"
    )
    op.drop_table("caregiver_alert_preference")
    op.drop_index("uq_caregiver_alert_link_type_dedupe", table_name="caregiver_alert")
    op.drop_index("ix_caregiver_alert_patient_id", table_name="caregiver_alert")
    op.drop_index("ix_caregiver_alert_caregiver_link_id", table_name="caregiver_alert")
    op.drop_table("caregiver_alert")
    sa.Enum(name="caregiver_alert_type").drop(op.get_bind(), checkfirst=False)
