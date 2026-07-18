"""Psychometrics item-bank + administration seam (ADR-0043, roadmap Spec 4).

These tests are mostly HONESTY GUARDS: the bank must stay uncalibrated, nothing may claim a
validated instrument, the administration stub must not claim IRT/CAT, and the bank must be
in parity with the polarity/scale/identity the rest of the app already uses — so this
scaffolding can never silently start overclaiming.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.ingestion.adl import (
    _DISPLAYS,
    SYMPTOM_CODES,
    SYMPTOM_NUMBNESS_CODE,
    SYMPTOM_PAIN_CODE,
    symptom_check_in_to_observations,
)
from app.psychometrics import (
    SYMPTOM_ITEM_BANK,
    FixedOrderSelector,
    ItemCalibration,
    SumScoreEstimator,
)
from app.schemas.ingestion import SYMPTOM_NRS_MAX, AdlCheckInIn
from app.trajectory.directionality import polarity_for

# --------------------------------------------------------------------------------------
# Honesty guards: uncalibrated, not validated, not IRT.
# --------------------------------------------------------------------------------------


def test_bank_is_uncalibrated_today() -> None:
    assert SYMPTOM_ITEM_BANK.is_calibrated is False
    for item in SYMPTOM_ITEM_BANK.items:
        assert item.calibration.is_calibrated is False
        assert item.calibration.discrimination is None
        assert item.calibration.thresholds is None
        assert item.calibration.model is None


def test_calibration_flips_only_with_real_parameters() -> None:
    # An uncalibrated item cannot be coaxed into is_calibrated without BOTH params.
    assert ItemCalibration().is_calibrated is False
    assert ItemCalibration(discrimination=1.0).is_calibrated is False  # slope alone: not enough
    assert ItemCalibration(discrimination=1.0, thresholds=(0.0, 1.0)).is_calibrated is True


def test_no_item_claims_a_validated_instrument() -> None:
    for item in SYMPTOM_ITEM_BANK.items:
        assert item.validated_instrument is False


def test_administration_stub_never_claims_adaptive_or_irt() -> None:
    selector = FixedOrderSelector(bank=SYMPTOM_ITEM_BANK)
    estimator = SumScoreEstimator()
    assert selector.is_adaptive is False
    assert estimator.is_irt is False
    # Fixed order == the bank's declared order (no adaptivity).
    assert selector.order() == SYMPTOM_ITEM_BANK.codes()
    # The estimator is a raw sum, not an ability estimate.
    assert estimator.score({SYMPTOM_PAIN_CODE: 7.0, SYMPTOM_NUMBNESS_CODE: 4.0}) == 11.0


# --------------------------------------------------------------------------------------
# Parity: the bank must agree with the rest of the app (polarity, scale, identity).
# --------------------------------------------------------------------------------------


def test_bank_polarity_matches_directionality_registry() -> None:
    # Spec 4 parity test: the item bank's polarity string must equal the shared Polarity
    # the trajectory engine already uses for the same code (StrEnum equality).
    for item in SYMPTOM_ITEM_BANK.items:
        assert item.polarity == polarity_for(item.code)


def test_bank_scale_matches_schema_validation_max() -> None:
    for item in SYMPTOM_ITEM_BANK.items:
        assert item.scale_min == 0
        assert item.scale_max == SYMPTOM_NRS_MAX


def test_bank_is_the_single_source_of_symptom_codes_and_displays() -> None:
    assert SYMPTOM_ITEM_BANK.codes() == SYMPTOM_CODES
    assert SYMPTOM_CODES == (SYMPTOM_PAIN_CODE, SYMPTOM_NUMBNESS_CODE)
    for item in SYMPTOM_ITEM_BANK.items:
        assert _DISPLAYS[item.code] == item.display


# --------------------------------------------------------------------------------------
# No behavior change: the scored fields of the emitted Observations are unchanged; the ADA
# keys are purely additive.
# --------------------------------------------------------------------------------------


def test_symptom_rows_keep_scored_fields_and_add_ada_keys() -> None:
    rows = symptom_check_in_to_observations(
        AdlCheckInIn(walking=2, stairs=2, balance_confidence=2, pain=7, numbness=4),
        patient_id=uuid4(),
        effective_at=datetime(2026, 7, 18, tzinfo=UTC),
        revises={},
    )
    by_code = {row.code: row for row in rows}
    assert set(by_code) == {SYMPTOM_PAIN_CODE, SYMPTOM_NUMBNESS_CODE}
    pain = by_code[SYMPTOM_PAIN_CODE]
    # Scored/identity fields the NSI + trajectory read — unchanged.
    assert pain.value_num == 7.0
    assert pain.unit == "{score}"
    assert pain.quality["polarity"] == "lower_is_better"
    assert pain.quality["scale_max"] == 10
    assert pain.quality["instrument"] == "symptom-check-in"
    assert pain.quality["validated_instrument"] is False
    # Additive ADA construct keys (ADR-0043).
    assert pain.quality["construct"] == "small_fiber_symptom"
    assert pain.quality["ada_fiber_class"] == "small_fiber"
    assert pain.quality["patient_reported"] is True
    assert "Rec 12.17" in pain.quality["ada_reference"]
