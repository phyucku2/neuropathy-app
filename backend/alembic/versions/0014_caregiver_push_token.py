"""Caregiver Companion Phase B2 (ADR-0047) — caregiver device push-token table.

Adds ``caregiver_push_token``: one row per (caregiver, device) FCM registration token,
FK the caregiver's ``app_user`` row. ``token`` is globally UNIQUE
(``uq_caregiver_push_token_token``), which powers the insert-first upsert (a device
re-registering / a token refresh updates in place) and the ``UNREGISTERED`` delete-by-
token cleanup the FCM fan-out runs. No new enum type.

Downgrade drops the indexes then the table.

Hand-written to match Base.metadata exactly (the integration suite verifies parity by
asserting autogenerate produces an empty diff against an upgraded database).

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "caregiver_push_token",
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
        sa.Column("caregiver_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token", sa.String(length=4096), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["caregiver_user_id"], ["app_user.id"]),
    )
    op.create_index(
        "ix_caregiver_push_token_caregiver_user_id",
        "caregiver_push_token",
        ["caregiver_user_id"],
        unique=False,
    )
    # The device registration token is globally unique — the insert-first upsert and the
    # UNREGISTERED delete-by-token cleanup both rely on it.
    op.create_index(
        "uq_caregiver_push_token_token",
        "caregiver_push_token",
        ["token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_caregiver_push_token_token", table_name="caregiver_push_token")
    op.drop_index("ix_caregiver_push_token_caregiver_user_id", table_name="caregiver_push_token")
    op.drop_table("caregiver_push_token")
