"""Hardening stores — durable pending-auth handshakes + encrypted token vault (ADR-0017).

Hand-written to match Base.metadata exactly (the integration suite verifies parity by
asserting autogenerate produces an empty diff against an upgraded database).

Creates two tables:

- pending_auth: one row per in-flight SMART OAuth handshake (state PK, PKCE verifier,
  token endpoint, connection FK, TTL). Rows are consumed atomically by the first
  callback (DELETE ... RETURNING) and expire after settings.pending_auth_ttl_seconds.
- secret: the encrypted-at-rest OAuth token vault (ref PK, Fernet ciphertext). Only
  ciphertext ever lands here; without a configured SECRET_STORE_KEY the app keeps the
  in-memory vault instead of writing plaintext.

Also adds ix_audit_event_actor_action_time: the invitation rate limiter counts one
actor's audit events per action inside a sliding window on every gated request.

Downgrade drops all three. That forfeits in-flight OAuth handshakes (patients restart the
connect flow) and vaulted tokens (patients re-link their EMR) — transient/re-obtainable
state, never health data, so unlike 0002 there is nothing to refuse over.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The invitation rate limiter counts (actor, action, occurred_at) on every gated
    # request; without this the count would range-scan ix_audit_event_occurred_at.
    op.create_index(
        "ix_audit_event_actor_action_time",
        "audit_event",
        ["actor_id", "action", "occurred_at"],
        unique=False,
    )

    op.create_table(
        "pending_auth",
        sa.Column("state", sa.String(length=128), primary_key=True),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_verifier", sa.String(length=256), nullable=False),
        sa.Column("token_endpoint", sa.String(length=400), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["emr_connection.id"]),
    )
    # The opportunistic purge deletes by expiry; keep it an index scan.
    op.create_index("ix_pending_auth_expires_at", "pending_auth", ["expires_at"], unique=False)

    op.create_table(
        "secret",
        sa.Column("ref", sa.String(length=200), primary_key=True),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    # Both tables hold only transient, re-obtainable OAuth state (handshakes in
    # flight; tokens the patient can re-grant by reconnecting) — never health data.
    op.drop_table("secret")
    op.drop_index("ix_pending_auth_expires_at", table_name="pending_auth")
    op.drop_table("pending_auth")
    op.drop_index("ix_audit_event_actor_action_time", table_name="audit_event")
