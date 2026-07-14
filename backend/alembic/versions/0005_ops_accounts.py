"""Ops-auth surface — per-account activation flag for operator revocation (ADR-0019).

Hand-written to match Base.metadata exactly (the integration suite verifies parity by
asserting autogenerate produces an empty diff against an upgraded database).

Adds two columns to app_user:

- active (boolean, NOT NULL, server_default true): a deactivated account fails login
  and every role gate. server_default true so the column can be added NOT NULL over any
  existing rows — all pre-existing accounts stay active.
- disabled_at (timestamptz, nullable): when the account was deactivated, NULL while
  active.

Introduced for ops operators — per-operator revocation the shared OPS_BOOTSTRAP_TOKEN
never had — but the flag is general to app_user, so any account can be disabled. The
user_role enum already carries 'ops' (migration 0001), so no enum change is needed.

Downgrade drops both columns. That forfeits only the activation state — accounts
themselves and their credentials are untouched — so unlike 0002 there is nothing to
refuse over.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "app_user",
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("app_user", "disabled_at")
    op.drop_column("app_user", "active")
