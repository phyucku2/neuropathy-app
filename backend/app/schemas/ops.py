"""API contracts for the ops-auth surface (ADR-0019): operator account provisioning
and per-operator deactivation."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field


class OpsAccountCreateIn(BaseModel):
    email: EmailStr
    # NIST 800-63B: length over composition rules (same bar as every other account).
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=200)


class OpsAccountOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    active: bool
