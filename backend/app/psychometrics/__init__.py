"""Psychometrics — the symptom item-bank and administration seam (ADR-0043, roadmap Spec 4).

Deterministic and UNCALIBRATED today: it is the single source of truth for the
patient-reported symptom items (identity, polarity, honest measure-alignment, and ADA
construct mapping) and a fixed-order / sum-score administration stub. It carries NO IRT
calibration and no consumer may claim IRT/CAT while the bank is uncalibrated. When real
calibration data lands, the `ItemCalibration` fields fill in — a data change, not a code
change — and adaptive selection becomes a new selector behind the same seam.

Zero behavior change: `app.ingestion.adl` derives its symptom codes/displays/alignment from
this bank and emits byte-identical scored Observations (plus additive ADA provenance keys).
The NSI never reads any of this, so the computed score is provably unchanged.
"""

from app.psychometrics.administration import FixedOrderSelector, SumScoreEstimator
from app.psychometrics.item_bank import (
    SYMPTOM_ITEM_BANK,
    ItemBank,
    ItemCalibration,
    SymptomItem,
)

__all__ = [
    "SYMPTOM_ITEM_BANK",
    "FixedOrderSelector",
    "ItemBank",
    "ItemCalibration",
    "SumScoreEstimator",
    "SymptomItem",
]
