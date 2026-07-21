"""Add the emr_clinical_note append-only store + the note-pull watermark (ADR-0045 P2 #27).

Clinical notes pulled from a patient's EMR via SMART on FHIR DocumentReference live in
their OWN append-only table (never on `observation`): large, sensitive free-text that may
mention unrelated conditions, carrying EXISTENCE + METADATA only (the body is never
stored). Import idempotency is a DB-level invariant via a partial UNIQUE index on
(patient_id, import_key) WHERE import_key IS NOT NULL, mirroring
uq_observation_patient_import_key.

Also adds `emr_connection.last_notes_pulled_at` — the incremental-pull watermark
(date=ge(this) on the next DocumentReference search).

Hand-written to match Base.metadata exactly (the integration suite verifies parity by
asserting autogenerate produces an empty diff against an upgraded database). The `origin`
column reuses the existing `data_origin` enum type (create_type=False — the type already
exists from 0001; a second CREATE TYPE would fail).

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "emr_clinical_note",
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
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "origin",
            # Reuse the existing enum type — do NOT re-create it (0001 already did).
            postgresql.ENUM(name="data_origin", create_type=False),
            nullable=False,
        ),
        sa.Column("source_system", sa.String(length=400), nullable=True),
        sa.Column("document_fhir_id", sa.String(length=200), nullable=True),
        sa.Column("type_code", sa.String(length=80), nullable=True),
        sa.Column("type_display", sa.String(length=200), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("authored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("author_display", sa.String(length=200), nullable=True),
        sa.Column("encounter_fhir_id", sa.String(length=200), nullable=True),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("attachment_url", sa.String(length=600), nullable=True),
        sa.Column("has_inline_data", sa.Boolean(), nullable=False),
        sa.Column("import_key", sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patient.id"]),
        sa.ForeignKeyConstraint(["connection_id"], ["emr_connection.id"]),
    )
    op.create_index(
        "ix_emr_clinical_note_patient_id", "emr_clinical_note", ["patient_id"], unique=False
    )
    op.create_index(
        "ix_emr_clinical_note_connection_id", "emr_clinical_note", ["connection_id"], unique=False
    )
    # The DB-level import-idempotency invariant (partial unique, mirrors observation).
    op.create_index(
        "uq_emr_note_patient_import_key",
        "emr_clinical_note",
        ["patient_id", "import_key"],
        unique=True,
        postgresql_where=sa.text("import_key IS NOT NULL"),
    )
    # The incremental note-pull watermark on the connection.
    op.add_column(
        "emr_connection",
        sa.Column("last_notes_pulled_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("emr_connection", "last_notes_pulled_at")
    op.drop_index("uq_emr_note_patient_import_key", table_name="emr_clinical_note")
    op.drop_index("ix_emr_clinical_note_connection_id", table_name="emr_clinical_note")
    op.drop_index("ix_emr_clinical_note_patient_id", table_name="emr_clinical_note")
    op.drop_table("emr_clinical_note")
