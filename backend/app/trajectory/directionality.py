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
import re
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
# Symptom check-in (POST /adl, ADR-0034 Phase 1): pain + numbness/paresthesia, higher =
# WORSE, so lower_is_better here inverts them into the shared better/worse judgment.
# Distinct label from the latent lab-side `_PAIN` ("pain") so the self-reported symptom
# trend ("nerve pain") never renders as a second, indistinguishable "pain" line.
_SYMPTOM_PAIN = SignalInfo(Polarity.lower_is_better, "nerve pain")
_SYMPTOM_NUMBNESS = SignalInfo(Polarity.lower_is_better, "numbness or tingling")
# BioMech balance/gait report metrics (ADR-0014). Polarities mirror the parser's
# METRICS registry (app/biomech/parser.py); a parity test keeps the two in agreement.
# Cadence and step length have no clear better/worse direction — reported, not judged.
_BIOMECH_BALANCE = SignalInfo(Polarity.higher_is_better, "balance")
_BIOMECH_SWAY_VELOCITY = SignalInfo(Polarity.lower_is_better, "sway speed")
_BIOMECH_SWAY_AREA = SignalInfo(Polarity.lower_is_better, "sway area")
_BIOMECH_GAIT_SPEED = SignalInfo(Polarity.higher_is_better, "walking speed")
_BIOMECH_CADENCE = SignalInfo(Polarity.unknown, "steps per minute")
_BIOMECH_STEP_LENGTH = SignalInfo(Polarity.unknown, "step length")
_BIOMECH_STEP_SYMMETRY = SignalInfo(Polarity.higher_is_better, "walking symmetry")

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
    # Symptom check-in (POST /adl, ADR-0034 Phase 1) — higher raw = worse, inverted here.
    "symptom_pain": _SYMPTOM_PAIN,
    "symptom_numbness": _SYMPTOM_NUMBNESS,
    # BioMech report metrics (source='biomech'), friendly keys — code_system stays null
    # like the other non-lab codes. Trends read as "balance up 8 over 30 days".
    "biomech_balance_score": _BIOMECH_BALANCE,
    "biomech_sway_velocity": _BIOMECH_SWAY_VELOCITY,
    "biomech_sway_area": _BIOMECH_SWAY_AREA,
    "biomech_gait_speed": _BIOMECH_GAIT_SPEED,
    "biomech_cadence": _BIOMECH_CADENCE,
    "biomech_step_length": _BIOMECH_STEP_LENGTH,
    "biomech_step_time_symmetry": _BIOMECH_STEP_SYMMETRY,
}


_SAFE_LABEL = re.compile(r"^[a-z0-9][a-z0-9 \-]{0,39}$")


def signal_info(code: str) -> SignalInfo:
    """Look up a signal's polarity + label; unknown codes get a safe default.

    Labels reach per-signal details, data gaps, and (via the facts payload) the AI
    narrative prompt, so a label derived from an unknown code is sanitized: short,
    lowercase alphanumerics only — anything else gets a generic label. Codes are
    validated at intake too (schemas/lab.py); this is defense in depth against
    prompt injection through free-text codes (ADR-0011 review finding).
    """
    known = _REGISTRY.get(code.lower())
    if known is not None:
        return known
    candidate = code.replace("_", " ").replace(".", " ").lower().strip()
    if _SAFE_LABEL.fullmatch(candidate):
        return SignalInfo(Polarity.unknown, candidate)
    return SignalInfo(Polarity.unknown, "one of your results")


def polarity_for(code: str) -> Polarity:
    """The registered polarity for a code, or `unknown` when unregistered."""
    return signal_info(code).polarity
