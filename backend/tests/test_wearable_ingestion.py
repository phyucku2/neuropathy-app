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


def test_mixed_tz_window_raises_valueerror_not_typeerror() -> None:
    # One bound naive, one aware — must fail cleanly as a WearableValueError (→ 422),
    # never a TypeError from comparing offset-naive to offset-aware (→ 500).
    naive_start = datetime(2026, 7, 15, 8, 5)  # naive, and AFTER the aware end
    with pytest.raises(WearableValueError):
        wearable_sample_to_observation(
            _sample(start=naive_start, end=END), patient_id=PATIENT_ID, import_key="k"
        )


def test_out_of_range_message_carries_no_measured_value() -> None:
    # The value is PHI; the error message must not echo it (audit/PHI contract).
    with pytest.raises(WearableValueError) as exc:
        wearable_sample_to_observation(
            _sample(WearableMetric.walking_speed, 8.7), patient_id=PATIENT_ID, import_key="k"
        )
    assert "8.7" not in str(exc.value)


# --- idempotency key -------------------------------------------------------------------


def test_import_key_prefers_platform_uuid() -> None:
    key = wearable_import_key(_sample(external_id="HK-abc"))
    assert key == "wearable:apple_health:id:HK-abc:wearable_walking_speed"


def test_same_external_id_different_metric_does_not_collide() -> None:
    # A client may derive external_id from a walking-BOUT, so two metrics can share it.
    # The metric is bound into the key so they never collapse into one (silent data loss).
    speed = wearable_import_key(_sample(WearableMetric.walking_speed, external_id="BOUT-1"))
    length = wearable_import_key(_sample(WearableMetric.step_length, external_id="BOUT-1"))
    assert speed != length


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


# --- continuous glucose (CGM, ADR-0038) ------------------------------------------------
# Glucose rides the SAME seam as mobility: device-measured, canonical mg/dL (the native
# seam converts mmol/L at the edge, so the backend only ever sees mg/dL), reliable fidelity,
# in_range_is_better polarity, PHI-free validation. It is NOT folded into the NSI (see
# test_trajectory_composite.py). No alarms, no dosing — a tracked signal only.


def test_glucose_maps_to_a_reliable_mg_dl_row() -> None:
    row = wearable_sample_to_observation(
        _sample(WearableMetric.blood_glucose, 120.0, external_id="CGM-1"),
        patient_id=PATIENT_ID,
        import_key="k",
    )
    assert row.code == "blood_glucose"
    assert row.source is SourceType.wearable
    assert row.origin is DataOrigin.device_measured
    assert row.status is ObservationStatus.final
    assert row.recorded_by_role == "patient"
    assert row.value_num == 120.0
    # Canonical unit from the catalog, never the client — the backend only sees mg/dL.
    assert row.unit == "mg/dL"
    # Device-measured CGM reading -> reliable (unlike the advisory mobility metrics).
    assert row.quality["fidelity"] == "reliable"
    assert row.quality["platform"] == "apple_health"
    assert row.payload["display"] == "Blood glucose"


def test_glucose_polarity_is_in_range_via_registry() -> None:
    # A high OR a low reading is worse: in_range_is_better, judged only by the registry.
    assert polarity_for("blood_glucose") is Polarity.in_range_is_better
    # Plain-language label, never the raw code (patient-facing).
    assert signal_info("blood_glucose").label == "blood sugar"


def test_glucose_out_of_range_is_skipped_with_a_value_free_warning() -> None:
    # An implausible mg/dL reading (> 600) is rejected, never coerced — and the measured
    # value is PHI, so it must not echo into the warning/error (audit contract, ADR-0038).
    with pytest.raises(WearableValueError, match="outside the expected range") as exc:
        wearable_sample_to_observation(
            _sample(WearableMetric.blood_glucose, 999.0), patient_id=PATIENT_ID, import_key="k"
        )
    assert "999" not in str(exc.value)


def test_glucose_import_key_prefers_platform_uuid() -> None:
    # Idempotency by platform sample identity, exactly like the mobility metrics.
    key = wearable_import_key(_sample(WearableMetric.blood_glucose, 120.0, external_id="CGM-9"))
    assert key == "wearable:apple_health:id:CGM-9:blood_glucose"
