"""API schemas for wearable/phone health-data ingestion (ADR-0035, Phase 1).

The real-world **ADL tier**: mobility samples imported from the platform health store
(Apple HealthKit / Android Health Connect) — the phone is the base, a watch is optional.
These are the passive counterpart to the self-reported ADL check-in (ADR-0006) and the
device-grade BioMech clinical tier (ADR-0014).

Design decisions baked into this contract:

- **The metric determines the unit** — the client sends a `metric` from a CLOSED set and a
  numeric `value`; the canonical unit comes from the server-side catalog
  (`app/ingestion/wearable.WEARABLE_METRICS`), never from the client. This is a deliberate
  application of the BioMech step-length lesson (feet vs cm): a client can never introduce
  a unit-confusion bug, because it never names the unit.
- **Fidelity is first-class.** Verified (deep-research 2026-07-16): iPhone-alone **walking
  speed and step length are well-validated**, but **walking asymmetry and double-support
  are weak phone-alone**. Each metric carries a fidelity tier so a downstream consumer (the
  NSI) can weight or exclude low-fidelity signals — the ingestion layer stores the truth and
  never silently treats an advisory signal as device-grade.
- **Phone vs. watch is recorded** (`phone_derived`, `source_device`) so the base-vs-optional
  distinction is preserved as provenance.
- **Idempotent** — a platform sample UUID (`external_id`) or, failing that, content identity
  keys the row, so re-syncing the same day never double-counts.
"""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field

# A daily sync can carry many short walking-bout samples across several metrics; cap the
# batch at a generous-but-bounded size so one request is never an implausible flood.
MAX_WEARABLE_BATCH = 500


class WearableMetric(enum.StrEnum):
    """The closed set of health-bridge metrics V1 ingests. The mobility codes are prefixed
    `wearable_` so they pool separately from BioMech (`biomech_`) and self-report (`adl_`)
    codes; `blood_glucose` (ADR-0038) keeps its bare canonical code, matching the ADR and
    the labs/CGM naming. The canonical unit, valid range, polarity, and fidelity of each
    live in the catalog (`app/ingestion/wearable.WEARABLE_METRICS`) — the single source of
    truth."""

    walking_speed = "wearable_walking_speed"
    step_length = "wearable_step_length"
    steps = "wearable_steps"
    walking_distance = "wearable_walking_distance"
    walking_asymmetry = "wearable_walking_asymmetry"
    double_support = "wearable_double_support"
    walking_steadiness = "wearable_walking_steadiness"
    # Continuous glucose (CGM) via the same health bridge (ADR-0038). Not a mobility metric
    # and not folded into the NSI in v1 — a tracked, graphed signal only. The native seam
    # canonicalizes to mg/dL at the edge, so the backend only ever sees mg/dL.
    blood_glucose = "blood_glucose"


class HealthPlatform(enum.StrEnum):
    """Which platform health store the sample came from."""

    apple_health = "apple_health"
    health_connect = "health_connect"


class SourceDevice(enum.StrEnum):
    """The device that produced the sample — preserves the phone-base vs watch-optional
    distinction as provenance (ADR-0035)."""

    iphone = "iphone"
    apple_watch = "apple_watch"
    android_phone = "android_phone"
    wear_os = "wear_os"
    unknown = "unknown"


class WearableSampleIn(BaseModel):
    """One imported mobility sample over a walking-bout window.

    The client sends the `metric` (closed set) and `value` only — the unit is derived
    server-side from the catalog, so a unit-confusion bug is structurally impossible.
    """

    metric: WearableMetric
    value: float = Field(..., description="Value in the metric's canonical unit (see catalog)")
    # Mobility metrics are computed over a walking bout, not a single instant. Both bounds
    # are carried; effective_at on the stored row is the window END (when it completed).
    effective_start: datetime
    effective_end: datetime
    platform: HealthPlatform
    source_device: SourceDevice = SourceDevice.unknown
    # True when the sample was produced by the phone ALONE (no watch) — the base tier.
    phone_derived: bool = True
    # The platform's own stable sample identifier (HKSample.uuid / Health Connect
    # metadata.id), used for idempotency when present. Bounded to keep the key sane.
    external_id: str | None = Field(default=None, max_length=200)


class WearableImportIn(BaseModel):
    """A batch of mobility samples from one health-store sync."""

    samples: list[WearableSampleIn] = Field(..., min_length=1, max_length=MAX_WEARABLE_BATCH)


class WearableImportOut(BaseModel):
    """Import outcome: how many rows were persisted vs. already on file (idempotent)."""

    imported: int = Field(..., ge=0)
    skipped: int = Field(..., ge=0, description="Already imported (same sample identity)")
