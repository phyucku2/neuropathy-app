"""Which way is "better" for each signal — the judgment layer's ground truth.

A rising series is only "improving" if higher is actually better for that measure.
This registry maps signal codes (LOINC codes and friendly keys) to a polarity, with
neuropathy-relevant lab defaults. Codes we don't know get `Polarity.unknown`: their
trend is still reported (rising/falling) but never judged better or worse — guessing
a polarity would be a silent clinical claim (AI-Safety lens, Brainstorm #3).

Each entry also carries a plain-language label (6th-8th grade) so summaries and
details never surface raw codes to patients.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Polarity(enum.StrEnum):
    """How a signal's numeric direction maps to better/worse."""

    higher_is_better = "higher_is_better"
    lower_is_better = "lower_is_better"
    in_range_is_better = "in_range_is_better"
    unknown = "unknown"


@dataclass(frozen=True, slots=True)
class SignalInfo:
    """Polarity plus the plain-language name shown to patients."""

    polarity: Polarity
    label: str


# Neuropathy-relevant defaults. Keyed by lowercase code; LOINC codes and friendly
# keys point at the same entry so both ingestion paths judge identically.
_HBA1C = SignalInfo(Polarity.lower_is_better, "long-term blood sugar")
_B12 = SignalInfo(Polarity.in_range_is_better, "vitamin B12")
_EGFR = SignalInfo(Polarity.higher_is_better, "kidney function")
_GLUCOSE = SignalInfo(Polarity.in_range_is_better, "blood sugar")
_TSH = SignalInfo(Polarity.in_range_is_better, "thyroid level")
_FOLATE = SignalInfo(Polarity.in_range_is_better, "folate")
_VITAMIN_D = SignalInfo(Polarity.in_range_is_better, "vitamin D")
_BALANCE = SignalInfo(Polarity.higher_is_better, "balance")
_GAIT_SPEED = SignalInfo(Polarity.higher_is_better, "walking speed")
_DAILY_FUNCTION = SignalInfo(Polarity.higher_is_better, "daily function")
_PAIN = SignalInfo(Polarity.lower_is_better, "pain")
_WALKING = SignalInfo(Polarity.higher_is_better, "walking")
_STAIRS = SignalInfo(Polarity.higher_is_better, "stairs")
_BALANCE_CONFIDENCE = SignalInfo(Polarity.higher_is_better, "balance confidence")

_REGISTRY: dict[str, SignalInfo] = {
    # Labs — LOINC codes first, then friendly keys.
    "4548-4": _HBA1C,  # Hemoglobin A1c/Hemoglobin.total in Blood
    "hba1c": _HBA1C,
    "2132-9": _B12,  # Cobalamin (Vitamin B12) [Mass/volume] in Serum or Plasma
    "vitamin_b12": _B12,
    "b12": _B12,
    "62238-1": _EGFR,  # GFR/1.73 sq M predicted (CKD-EPI)
    "33914-3": _EGFR,  # GFR/1.73 sq M predicted (MDRD)
    "egfr": _EGFR,
    "2345-7": _GLUCOSE,  # Glucose [Mass/volume] in Serum or Plasma
    "1558-6": _GLUCOSE,  # Fasting glucose
    "glucose": _GLUCOSE,
    "3016-3": _TSH,  # Thyrotropin [Units/volume] in Serum or Plasma
    "tsh": _TSH,
    "2284-8": _FOLATE,  # Folate [Mass/volume] in Serum or Plasma
    "folate": _FOLATE,
    "1989-3": _VITAMIN_D,  # 25-Hydroxyvitamin D3
    "vitamin_d": _VITAMIN_D,
    # Functional / patient-reported signals (friendly keys).
    "balance_score": _BALANCE,
    "gait_speed": _GAIT_SPEED,
    "adl_katz": _DAILY_FUNCTION,
    "adl_barthel": _DAILY_FUNCTION,
    "pain_score": _PAIN,
    # ADL daily check-in (POST /adl): three 0-4 answers + the 0-12 derived composite.
    # All scored so that a higher number means better function.
    "adl_walking": _WALKING,
    "adl_stairs": _STAIRS,
    "adl_balance_confidence": _BALANCE_CONFIDENCE,
    "adl_daily_score": _DAILY_FUNCTION,
}


def signal_info(code: str) -> SignalInfo:
    """Look up a signal's polarity + label; unknown codes get a safe default.

    Unknown codes are labeled from the code itself (underscores become spaces) —
    that label may appear in per-signal details and data gaps, but an unjudged
    signal never drives the summary sentence.
    """
    known = _REGISTRY.get(code.lower())
    if known is not None:
        return known
    return SignalInfo(Polarity.unknown, code.replace("_", " "))


def polarity_for(code: str) -> Polarity:
    """The registered polarity for a code, or `unknown` when unregistered."""
    return signal_info(code).polarity
