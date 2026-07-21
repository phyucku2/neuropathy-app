"""Add the mfa_factor table — one enrolled TOTP factor per privileged user (§1B C6).

The row stores an opaque ``secret_ref`` into the SecretStore vault only — the TOTP
secret itself is Fernet-encrypted in the ``secret`` table (or the per-process fallback
vault), never in this table. ``user_id`` is UNIQUE: re-enrollment replaces the row.
``confirmed_at`` NULL means the enrollment is pending its first verified code and does
not step up login.

Hand-written to match Base.metadata exactly (the integration suite verifies parity by
asserting autogenerate produces an empty diff against an upgraded database).

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mfa_factor",
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
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("secret_ref", sa.String(length=200), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"]),
    )
    op.create_index("ix_mfa_factor_user_id", "mfa_factor", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_mfa_factor_user_id", table_name="mfa_factor")
    op.drop_table("mfa_factor")
