"""ADL daily check-in ingestion — three confirmed 0-4 answers plus a derived composite
mapped to research-grade Observation rows (ADR-0003, ADR-0006, ADR-0007).

The mapping is a pure function like the labs adapter: the route resolves which same-day
rows (if any) are being superseded, and this module builds the new rows. A same-day
re-submission never overwrites — each new row carries `revises_id` to the record it
replaces (corrections-as-new-records, ADR-0006), so the original endures and the chain
is the change history.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta

from app.fhir.resources import UCUM_SYSTEM
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.schemas.ingestion import (
    ADL_ANSWER_MAX,
    ADL_COMPOSITE_MAX,
    SYMPTOM_NRS_MAX,
    AdlCheckInIn,
)

# The three daily-function questions (mockups), each answered 0-4, higher = better.
ADL_ANSWER_CODES: tuple[str, str, str] = ("adl_walking", "adl_stairs", "adl_balance_confidence")
ADL_COMPOSITE_CODE = "adl_daily_score"
ADL_CODES: tuple[str, ...] = (*ADL_ANSWER_CODES, ADL_COMPOSITE_CODE)

# Symptom items (ADR-0034 Phase 1): pain + numbness/paresthesia, each 0-10 where HIGHER =
# WORSE — the inverse polarity of the function answers. Own codes so they pool separately;
# behind the `ingest_symptoms` toggle. Phase 1 stores only (no composite/normalization).
SYMPTOM_PAIN_CODE = "symptom_pain"
SYMPTOM_NUMBNESS_CODE = "symptom_numbness"
SYMPTOM_CODES: tuple[str, str] = (SYMPTOM_PAIN_CODE, SYMPTOM_NUMBNESS_CODE)

# UCUM annotation for a dimensionless score (annotations equal unity in UCUM).
_SCORE_UNIT = "{score}"

# Instrument identity + version: provenance names the exact protocol a datum came from
# (data-standards.md), so a future question change bumps the version, not the meaning.
_INSTRUMENT = "adl-daily-check-in"
_INSTRUMENT_VERSION = "1"

# Symptom capture is a SEPARATE instrument protocol from the function check-in.
_SYMPTOM_INSTRUMENT = "symptom-check-in"
_SYMPTOM_INSTRUMENT_VERSION = "1"

# Honest measure alignment (ADR-0034): the items are validated-measure-ALIGNED, not the
# copyrighted instruments themselves. NTSS-6 exact wording/scoring + licensing are not yet
# confirmed ("confirm against source"), so `validated_instrument` is False everywhere —
# nothing stored claims to BE NTSS-6 or a validated measure.
_SYMPTOM_ALIGNMENT: dict[str, str] = {
    SYMPTOM_PAIN_CODE: "NRS-aligned",  # 0-10 Numeric Rating Scale (public-domain)
    SYMPTOM_NUMBNESS_CODE: "NTSS-6-aligned",  # numbness/paresthesia severity item
}

_DISPLAYS: dict[str, str] = {
    "adl_walking": "Walking",
    "adl_stairs": "Stairs",
    "adl_balance_confidence": "Balance confidence",
    ADL_COMPOSITE_CODE: "Daily function score",
    SYMPTOM_PAIN_CODE: "Pain",
    SYMPTOM_NUMBNESS_CODE: "Numbness or tingling",
}


def day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """The UTC half-open interval [start, end) covering one calendar day."""
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _base_quality() -> dict[str, str]:
    return {
        "instrument": _INSTRUMENT,
        "instrument_version": _INSTRUMENT_VERSION,
        "method": "self_report",
    }


def adl_check_in_to_observations(
    check_in: AdlCheckInIn,
    *,
    patient_id: uuid.UUID,
    effective_at: datetime,
    revises: Mapping[str, uuid.UUID],
    recorded_at: datetime | None = None,
) -> list[Observation]:
    """Map one confirmed daily check-in to its four research-grade Observation rows.

    One row per answer (patient_reported) plus the composite daily score (derived —
    computed from the answers, with its derivation named in `quality`). `revises` maps
    codes to the same-day rows these new rows supersede; a revising row enters as
    `amended` (new information replacing the earlier answer, per FHIR lifecycle).
    """
    recorded = recorded_at or datetime.now(UTC)
    answers: dict[str, int] = {
        "adl_walking": check_in.walking,
        "adl_stairs": check_in.stairs,
        "adl_balance_confidence": check_in.balance_confidence,
    }

    def _row(
        code: str, value: int, *, origin: DataOrigin, quality: dict[str, object]
    ) -> Observation:
        revises_id = revises.get(code)
        return Observation(
            patient_id=patient_id,
            source=SourceType.adl,
            origin=origin,
            # Internal friendly keys (not LOINC); code_system stays null like the other
            # non-lab codes in the directionality registry.
            code=code,
            code_system=None,
            value_num=float(value),
            unit=_SCORE_UNIT,
            unit_system=UCUM_SYSTEM,
            effective_at=effective_at,
            recorded_at=recorded,
            status=ObservationStatus.amended if revises_id else ObservationStatus.final,
            revises_id=revises_id,
            recorded_by_role="patient",
            quality=quality,
            payload={
                "display": _DISPLAYS[code],
                "check_in_date": effective_at.date().isoformat(),
            },
        )

    rows = [
        _row(
            code,
            value,
            origin=DataOrigin.patient_reported,
            quality={**_base_quality(), "scale_max": ADL_ANSWER_MAX},
        )
        for code, value in answers.items()
    ]
    rows.append(
        _row(
            ADL_COMPOSITE_CODE,
            sum(answers.values()),
            origin=DataOrigin.derived,
            quality={
                **_base_quality(),
                "scale_max": ADL_COMPOSITE_MAX,
                "derivation": "sum",
                "derived_from": list(ADL_ANSWER_CODES),
            },
        )
    )
    return rows


def symptom_check_in_to_observations(
    check_in: AdlCheckInIn,
    *,
    patient_id: uuid.UUID,
    effective_at: datetime,
    revises: Mapping[str, uuid.UUID],
    recorded_at: datetime | None = None,
) -> list[Observation]:
    """Map the OPTIONAL symptom items (pain, numbness) to research-grade Observation rows.

    One patient-reported row per item that was answered — an unanswered item yields no
    row. Each row records the HIGHER-IS-WORSE polarity explicitly in `quality` (so Phase
    2's normalization inverts it correctly) and the honest measure alignment (NRS /
    NTSS-6-*aligned*, `validated_instrument=False`). Like the function answers, a same-day
    re-submission supersedes via `revises_id` (corrections-as-new-records, ADR-0006).

    The caller (route) only invokes this when the `ingest_symptoms` capability is on for
    the patient (ADR-0013 enforced-flag honesty); when off, symptom answers are never
    persisted regardless of what the client sends.
    """
    recorded = recorded_at or datetime.now(UTC)
    values: dict[str, int | None] = {
        SYMPTOM_PAIN_CODE: check_in.pain,
        SYMPTOM_NUMBNESS_CODE: check_in.numbness,
    }
    rows: list[Observation] = []
    for code, value in values.items():
        if value is None:
            continue
        revises_id = revises.get(code)
        rows.append(
            Observation(
                patient_id=patient_id,
                source=SourceType.adl,
                origin=DataOrigin.patient_reported,
                code=code,
                code_system=None,
                value_num=float(value),
                unit=_SCORE_UNIT,
                unit_system=UCUM_SYSTEM,
                effective_at=effective_at,
                recorded_at=recorded,
                status=ObservationStatus.amended if revises_id else ObservationStatus.final,
                revises_id=revises_id,
                recorded_by_role="patient",
                quality={
                    "instrument": _SYMPTOM_INSTRUMENT,
                    "instrument_version": _SYMPTOM_INSTRUMENT_VERSION,
                    "method": "self_report",
                    "scale_min": 0,
                    "scale_max": SYMPTOM_NRS_MAX,
                    # Symptom polarity: higher raw = worse. Recorded so Phase 2 inverts it
                    # (never bake normalization into Phase 1).
                    "polarity": "lower_is_better",
                    "higher_is_worse": True,
                    # Honest instrument mapping (ADR-0034): aligned, NOT the validated
                    # instrument — exact NTSS-6 items/scoring + licensing unconfirmed.
                    "measure_alignment": _SYMPTOM_ALIGNMENT[code],
                    "validated_instrument": False,
                },
                payload={
                    "display": _DISPLAYS[code],
                    "check_in_date": effective_at.date().isoformat(),
                },
            )
        )
    return rows
