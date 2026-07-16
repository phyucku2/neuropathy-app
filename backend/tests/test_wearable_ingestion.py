"""Unit tests for the wearable/phone mobility mapping (ADR-0035 Phase 1).

Pure mapping only — no client, no DB. All data synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.ingestion.wearable import (
    WEARABLE_METRICS,
    Fidelity,
    WearableValueError,
    wearable_import_key,
    wearable_sample_to_observation,
)
from app.models.observation import DataOrigin, ObservationStatus, SourceType
from app.schemas.wearable import (
    HealthPlatform,
    SourceDevice,
    WearableMetric,
    WearableSampleIn,
)
from app.trajectory.directionality import Polarity, polarity_for, signal_info

PATIENT_ID = uuid4()
START = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)
END = datetime(2026, 7, 15, 8, 3, tzinfo=UTC)


def _sample(
    metric: WearableMetric = WearableMetric.walking_speed,
    value: float = 1.1,
    *,
    platform: HealthPlatform = HealthPlatform.apple_health,
    source_device: SourceDevice = SourceDevice.iphone,
    phone_derived: bool = True,
    external_id: str | None = None,
    start: datetime = START,
    end: datetime = END,
) -> WearableSampleIn:
    return WearableSampleIn(
        metric=metric,
        value=value,
        effective_start=start,
        effective_end=end,
        platform=platform,
        source_device=source_device,
        phone_derived=phone_derived,
        external_id=external_id,
    )


# --- catalog integrity -----------------------------------------------------------------


def test_catalog_covers_every_metric_code() -> None:
    # Every enum member has a spec, and every spec code is in the directionality registry
    # (so a trend can be judged), keeping the three sources of truth in lockstep.
    assert set(WEARABLE_METRICS) == set(WearableMetric)
    for metric in WearableMetric:
        assert polarity_for(metric.value) is not Polarity.unknown, metric


def test_fidelity_matches_the_verified_evidence() -> None:
    # Verified 2026-07-16: speed/step-length reliable phone-alone; asymmetry/double-support
    # weak (advisory); step/distance are quantity measures.
    assert WEARABLE_METRICS[WearableMetric.walking_speed].fidelity is Fidelity.reliable
    assert WEARABLE_METRICS[WearableMetric.step_length].fidelity is Fidelity.reliable
    assert WEARABLE_METRICS[WearableMetric.walking_asymmetry].fidelity is Fidelity.advisory
    assert WEARABLE_METRICS[WearableMetric.double_support].fidelity is Fidelity.advisory
    assert WEARABLE_METRICS[WearableMetric.steps].fidelity is Fidelity.quantity


def test_polarity_of_advisory_metrics_is_lower_is_better() -> None:
    # Higher asymmetry / double-support = worse; polarity is correct regardless of fidelity.
    assert polarity_for("wearable_walking_asymmetry") is Polarity.lower_is_better
    assert polarity_for("wearable_double_support") is Polarity.lower_is_better
    assert polarity_for("wearable_walking_speed") is Polarity.higher_is_better
    # Plain-language label, never the raw code (patient-facing).
    assert signal_info("wearable_walking_speed").label == "walking speed"


# --- mapping ---------------------------------------------------------------------------


def test_maps_to_a_research_grade_row() -> None:
    row = wearable_sample_to_observation(
        _sample(external_id="HK-123"), patient_id=PATIENT_ID, import_key="k"
    )
    assert row.source is SourceType.wearable
    assert row.origin is DataOrigin.device_measured
    assert row.status is ObservationStatus.final
    assert row.recorded_by_role == "patient"
    assert row.code == "wearable_walking_speed"
    assert row.value_num == 1.1
    # The unit comes from the catalog, never the client (the feet-vs-cm lesson).
    assert row.unit == "m/s"
    # effective_at is the walking-bout END; the full window is in quality.
    assert row.effective_at == END
    assert row.quality["effective_start"] == START.isoformat()
    assert row.quality["effective_end"] == END.isoformat()
    assert row.quality["platform"] == "apple_health"
    assert row.quality["source_device"] == "iphone"
    assert row.quality["phone_derived"] is True
    assert row.quality["fidelity"] == "reliable"
    assert row.payload["display"] == "Walking speed"


def test_advisory_metric_carries_advisory_fidelity() -> None:
    row = wearable_sample_to_observation(
        _sample(WearableMetric.walking_asymmetry, 4.5), patient_id=PATIENT_ID, import_key="k"
    )
    assert row.quality["fidelity"] == "advisory"
    assert row.unit == "%"


def test_naive_window_is_coerced_to_utc() -> None:
    row = wearable_sample_to_observation(
        _sample(start=datetime(2026, 7, 15, 8, 0), end=datetime(2026, 7, 15, 8, 3)),
        patient_id=PATIENT_ID,
        import_key="k",
    )
    assert row.effective_at.tzinfo is not None


# --- validation (reject, never coerce) -------------------------------------------------


def test_out_of_range_value_raises() -> None:
    with pytest.raises(WearableValueError, match="outside the expected range"):
        wearable_sample_to_observation(
            _sample(WearableMetric.walking_speed, 9.0), patient_id=PATIENT_ID, import_key="k"
        )


def test_negative_value_raises() -> None:
    with pytest.raises(WearableValueError):
        wearable_sample_to_observation(
            _sample(WearableMetric.steps, -1.0), patient_id=PATIENT_ID, import_key="k"
        )


def test_inverted_window_raises() -> None:
    with pytest.raises(WearableValueError, match="before effective_start"):
        wearable_sample_to_observation(
            _sample(start=END, end=START), patient_id=PATIENT_ID, import_key="k"
        )


# --- idempotency key -------------------------------------------------------------------


def test_import_key_prefers_platform_uuid() -> None:
    key = wearable_import_key(_sample(external_id="HK-abc"))
    assert key == "wearable:apple_health:id:HK-abc"


def test_import_key_falls_back_to_content_identity() -> None:
    key = wearable_import_key(_sample(value=1.1, external_id=None))
    assert key.startswith("wearable:apple_health:content:wearable_walking_speed:")
    # A different value is a different key (a correction is a new row, append-only).
    other = wearable_import_key(_sample(value=1.2, external_id=None))
    assert key != other


def test_same_uuid_same_key_across_value_changes() -> None:
    # Platform identity wins: the same sample UUID is the same row even if re-read.
    a = wearable_import_key(_sample(value=1.1, external_id="HK-x"))
    b = wearable_import_key(_sample(value=1.2, external_id="HK-x"))
    assert a == b
