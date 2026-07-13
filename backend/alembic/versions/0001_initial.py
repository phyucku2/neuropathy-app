"""Initial schema — all tables in app/models.

Hand-written to match Base.metadata exactly (the integration suite verifies parity by
asserting autogenerate produces an empty diff against an upgraded database).

Revision ID: 0001
Revises:
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUM_NAMES = (
    "connection_mode",
    "user_role",
    "actor",
    "connection_status",
    "initiator",
    "emr_connection_status",
    "source_type",
    "data_origin",
    "observation_status",
)


def upgrade() -> None:
    op.create_table(
        "patient",
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
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column(
            "connection_mode",
            sa.Enum("self_connected", "clinical", name="connection_mode"),
            nullable=False,
        ),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.create_table(
        "app_user",
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
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=300), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.Enum("patient", "clinician", "ops", name="user_role"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_app_user_email", "app_user", ["email"], unique=True)

    op.create_table(
        "capability",
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
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("key"),
    )

    op.create_table(
        "patient_capability",
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
        sa.Column("capability_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("set_by", sa.Enum("patient", "clinician", "ops", name="actor"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patient.id"]),
        sa.ForeignKeyConstraint(["capability_id"], ["capability.id"]),
        sa.UniqueConstraint("patient_id", "capability_id", name="uq_patient_capability"),
    )
    op.create_index(
        "ix_patient_capability_patient_id", "patient_capability", ["patient_id"], unique=False
    )

    op.create_table(
        "clinic_connection",
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
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "active", "revoked", name="connection_status"),
            nullable=False,
        ),
        sa.Column("initiated_by", sa.Enum("clinic", "patient", name="initiator"), nullable=False),
        sa.Column("consent_granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patient.id"]),
    )
    op.create_index(
        "ix_clinic_connection_clinic_id", "clinic_connection", ["clinic_id"], unique=False
    )
    op.create_index(
        "ix_clinic_connection_patient_id", "clinic_connection", ["patient_id"], unique=False
    )

    op.create_table(
        "emr_connection",
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
        sa.Column("fhir_base", sa.String(length=400), nullable=False),
        sa.Column("provider_name", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.Enum("authorizing", "active", "revoked", name="emr_connection_status"),
            nullable=False,
        ),
        sa.Column("granted_scope", sa.String(length=500), nullable=True),
        sa.Column("patient_fhir_id", sa.String(length=200), nullable=True),
        sa.Column("token_ref", sa.String(length=200), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patient.id"]),
    )
    op.create_index("ix_emr_connection_patient_id", "emr_connection", ["patient_id"], unique=False)

    op.create_table(
        "observation",
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
        sa.Column("source", sa.Enum("lab", "adl", name="source_type"), nullable=False),
        sa.Column(
            "origin",
            sa.Enum(
                "device_measured",
                "document_imported",
                "ehr_imported",
                "patient_reported",
                "derived",
                name="data_origin",
            ),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("code_system", sa.String(length=40), nullable=True),
        sa.Column("value_num", sa.Double(), nullable=True),
        sa.Column("value_text", sa.String(length=500), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("unit_system", sa.String(length=40), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "preliminary",
                "final",
                "amended",
                "corrected",
                "entered_in_error",
                name="observation_status",
            ),
            nullable=False,
        ),
        sa.Column("revises_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recorded_by_role", sa.String(length=32), nullable=True),
        sa.Column("import_key", sa.String(length=300), nullable=True),
        sa.Column("quality", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patient.id"]),
        sa.ForeignKeyConstraint(["revises_id"], ["observation.id"]),
    )
    op.create_index(
        "ix_observation_patient_code_time",
        "observation",
        ["patient_id", "code", "effective_at"],
        unique=False,
    )
    op.create_index("ix_observation_patient_id", "observation", ["patient_id"], unique=False)
    op.create_index(
        "ix_observation_patient_import_key",
        "observation",
        ["patient_id", "import_key"],
        unique=False,
    )
    op.create_index(
        "ix_observation_patient_revises", "observation", ["patient_id", "revises_id"], unique=False
    )
    op.create_index("ix_observation_status", "observation", ["status"], unique=False)

    op.create_table(
        "audit_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patient.id"]),
    )
    op.create_index("ix_audit_event_occurred_at", "audit_event", ["occurred_at"], unique=False)
    op.create_index("ix_audit_event_patient_id", "audit_event", ["patient_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_event_patient_id", table_name="audit_event")
    op.drop_index("ix_audit_event_occurred_at", table_name="audit_event")
    op.drop_table("audit_event")
    op.drop_index("ix_observation_status", table_name="observation")
    op.drop_index("ix_observation_patient_revises", table_name="observation")
    op.drop_index("ix_observation_patient_import_key", table_name="observation")
    op.drop_index("ix_observation_patient_id", table_name="observation")
    op.drop_index("ix_observation_patient_code_time", table_name="observation")
    op.drop_table("observation")
    op.drop_index("ix_emr_connection_patient_id", table_name="emr_connection")
    op.drop_table("emr_connection")
    op.drop_index("ix_clinic_connection_patient_id", table_name="clinic_connection")
    op.drop_index("ix_clinic_connection_clinic_id", table_name="clinic_connection")
    op.drop_table("clinic_connection")
    op.drop_index("ix_patient_capability_patient_id", table_name="patient_capability")
    op.drop_table("patient_capability")
    op.drop_table("capability")
    op.drop_index("ix_app_user_email", table_name="app_user")
    op.drop_table("app_user")
    op.drop_table("patient")
    for enum_name in _ENUM_NAMES:
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=False)
