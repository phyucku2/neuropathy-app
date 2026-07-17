"""Map an imported wearable/phone mobility sample to a research-grade Observation
(ADR-0035 Phase 1, ADR-0006).

Mirrors the labs/biomech adapters: a pure mapping function (fully unit-tested),
content-identity (or platform-UUID) idempotency, and full provenance. Every row is
``source=wearable``, ``origin=device_measured`` (a sensor on the patient's own device
produced it), ``recorded_by_role='patient'``.

The **catalog (``WEARABLE_METRICS``) is the single source of truth** for each metric's
display, canonical unit, valid range, and **fidelity tier** — the client never names a
unit (structurally preventing the feet-vs-cm class of bug), and the fidelity tier records
the verified reality that iPhone-alone walking speed/step-length are well-validated while
asymmetry/double-support are weak phone-alone, so a downstream consumer (the NSI) can
weight or exclude low-fidelity signals rather than treating them as device-grade.

This module is pure (no I/O); the route (app/api/routes/ingestion.py) persists the rows
with a PHI-free audit event.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.fhir.resources import UCUM_SYSTEM
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.schemas.wearable import WearableMetric, WearableSampleIn

_SOURCE_SYSTEM = "wearable-health"
_INSTRUMENT = "mobility-metrics"
_INSTRUMENT_VERSION = "1"


class Fidelity(enum.StrEnum):
    """How much measurement trust a metric warrants when produced by a phone alone.

    Orthogonal to polarity (which direction is *better*): fidelity is about measurement
    *accuracy*. Verified (deep-research 2026-07-16): phone-alone speed/step-length are
    well-validated (``reliable``); asymmetry/double-support are poor-to-moderate
    (``advisory``); step/distance counts are established quantity measures (``quantity``).
    Stored in every row's ``quality`` so the NSI can weight/exclude accordingly.
    """

    reliable = "reliable"
    quantity = "quantity"
    advisory = "advisory"


@dataclass(frozen=True, slots=True)
class MetricSpec:
    """One wearable metric: curated display, canonical unit (UCUM), valid range, and
    fidelity. Ranges are generous physiologic bounds — their job is to reject nonsense
    (a negative speed, a parse error), not to make a clinical judgment."""

    display: str
    unit: str
    min_value: float
    max_value: float
    fidelity: Fidelity


# The closed catalog V1 ingests. Units are canonical and authoritative: the client sends
# only the metric + value, so a unit-confusion bug is impossible by construction.
WEARABLE_METRICS: dict[WearableMetric, MetricSpec] = {
    WearableMetric.walking_speed: MetricSpec("Walking speed", "m/s", 0.0, 5.0, Fidelity.reliable),
    WearableMetric.step_length: MetricSpec("Step length", "m", 0.0, 2.0, Fidelity.reliable),
    WearableMetric.steps: MetricSpec("Daily steps", "{steps}", 0.0, 200000.0, Fidelity.quantity),
    WearableMetric.walking_distance: MetricSpec(
        "Walking distance", "m", 0.0, 200000.0, Fidelity.quantity
    ),
    WearableMetric.walking_asymmetry: MetricSpec(
        "Walking asymmetry", "%", 0.0, 100.0, Fidelity.advisory
    ),
    WearableMetric.double_support: MetricSpec(
        "Double-support time", "%", 0.0, 100.0, Fidelity.advisory
    ),
    WearableMetric.walking_steadiness: MetricSpec(
        "Walking steadiness", "%", 0.0, 100.0, Fidelity.advisory
    ),
    # Continuous glucose (CGM) via the health bridge (ADR-0038). Device-measured, so
    # `reliable`; unit is canonical mg/dL (the native seam converts mmol/L at the edge).
    # The range rejects nonsense (a negative or absurd reading), NOT a clinical judgment —
    # ~20-600 mg/dL spans severe hypo- to severe hyperglycemia; outliers are skipped with a
    # warning, never coerced (like every other metric). No alarms, no dosing (ADR-0038).
    WearableMetric.blood_glucose: MetricSpec(
        "Blood glucose", "mg/dL", 20.0, 600.0, Fidelity.reliable
    ),
}


class WearableValueError(ValueError):
    """A sample's value is outside the metric's valid range, or its window is invalid.

    Raised by the pure mapper so the route can translate it to a 422 without guessing —
    research-grade: reject a nonsensical measurement, never coerce or store it."""


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def wearable_import_key(sample: WearableSampleIn) -> str:
    """Stable idempotency key for one sample.

    Prefers the platform's own sample UUID (``external_id``) — the true identity of a
    HealthKit/Health Connect sample; re-syncing the same day yields the same key and is
    skipped. Without one, falls back to content identity (platform + metric + window +
    value), so a value never enters the analyzable dataset twice.
    """
    if sample.external_id:
        # Bind the metric even in the id branch: a client may (mistakenly) derive the id
        # from a walking-BOUT rather than the per-metric sample, so two different metrics
        # can share an external_id — without the metric they would collide and silently
        # drop one metric's datum (mirrors the content key + biomech_import_key, which both
        # bind the metric).
        return f"wearable:{sample.platform.value}:id:{sample.external_id}:{sample.metric.value}"
    # Provenance is part of identity: the same value at the same instant from a phone vs a
    # watch are distinct observations, so device + phone_derived join the content key.
    return (
        f"wearable:{sample.platform.value}:content:{sample.metric.value}"
        f":{_as_utc(sample.effective_start).isoformat()}:{_as_utc(sample.effective_end).isoformat()}"
        f":{sample.value}:{sample.source_device.value}:{sample.phone_derived}"
    )


def wearable_sample_to_observation(
    sample: WearableSampleIn,
    *,
    patient_id: uuid.UUID,
    import_key: str,
    recorded_at: datetime | None = None,
) -> Observation:
    """Map one imported mobility sample to a research-grade Observation row.

    ``source=wearable``, ``origin=device_measured``, ``status=final``. ``effective_at`` is
    the walking-bout END (when the metric completed); the full window, platform, device,
    phone-vs-watch derivation, and fidelity are recorded in ``quality``. The display comes
    only from the closed catalog, never from client text. Raises ``WearableValueError``
    when the value is out of range or the window is inverted (research-grade: reject,
    never coerce).
    """
    spec = WEARABLE_METRICS[sample.metric]
    # Compare NORMALIZED bounds: a client may send one bound naive and the other aware,
    # and comparing offset-naive to offset-aware datetimes raises TypeError (an uncaught
    # 500). Normalize first so a mixed-tz window fails cleanly as a 422, not a crash.
    if _as_utc(sample.effective_end) < _as_utc(sample.effective_start):
        raise WearableValueError(f"{spec.display}: effective_end is before effective_start")
    if not (spec.min_value <= sample.value <= spec.max_value):
        # The measured VALUE is PHI and must never cross into an error body/log (audit
        # contract). Report only the metric + the non-PHI catalog range.
        raise WearableValueError(
            f"{spec.display}: value is outside the expected range "
            f"{spec.min_value:g}–{spec.max_value:g}"
        )
    quality: dict[str, object] = {
        "source_system": _SOURCE_SYSTEM,
        "instrument": _INSTRUMENT,
        "instrument_version": _INSTRUMENT_VERSION,
        "method": "device_sensor",
        "platform": sample.platform.value,
        "source_device": sample.source_device.value,
        # Base-vs-optional (ADR-0035): whether the phone produced this without a watch.
        "phone_derived": sample.phone_derived,
        # Measurement trust, NOT a clinical judgment — lets the NSI weight/exclude.
        "fidelity": spec.fidelity.value,
        "effective_start": _as_utc(sample.effective_start).isoformat(),
        "effective_end": _as_utc(sample.effective_end).isoformat(),
    }
    return Observation(
        patient_id=patient_id,
        source=SourceType.wearable,
        origin=DataOrigin.device_measured,
        # Internal controlled-vocabulary code (like BioMech/ADL); code_system stays null.
        code=sample.metric.value,
        code_system=None,
        value_num=sample.value,
        unit=spec.unit,
        unit_system=UCUM_SYSTEM,
        effective_at=_as_utc(sample.effective_end),
        recorded_at=recorded_at or datetime.now(UTC),
        status=ObservationStatus.final,
        recorded_by_role="patient",
        import_key=import_key,
        quality=quality,
        payload={"display": spec.display},
    )
