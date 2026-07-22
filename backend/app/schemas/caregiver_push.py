"""API contracts for caregiver device push-token registration (ADR-0047 Phase B2).

No PHI: a device registration token is an opaque routing identifier. The register
endpoint returns only non-sensitive metadata (never the token back verbatim beyond what
the client already holds)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.base import ApiModel

PlatformLiteral = Literal["android"]


class CaregiverPushTokenIn(ApiModel):
    """Register/refresh a caregiver device token (native app, ADR-0047 B2)."""

    token: str = Field(min_length=1, max_length=4096)
    platform: PlatformLiteral


class CaregiverPushTokenDeleteIn(ApiModel):
    """Deregister a caregiver device token (logout / permission-off)."""

    token: str = Field(min_length=1, max_length=4096)


class CaregiverPushTokenOut(BaseModel):
    """The registered device token as the caregiver's client sees it — metadata only."""

    id: uuid.UUID
    platform: PlatformLiteral
    last_seen_at: datetime
    created_at: datetime
