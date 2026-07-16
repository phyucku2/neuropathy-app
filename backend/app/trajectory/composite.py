"""The Neuropathy Status Index (NSI) — a deterministic 0-100 composite (ADR-0034).

Higher = better health. The Index is a **non-diagnostic v1**, symptom-forward
composite over three domains (Symptoms 45 / Function 40 / Physiologic 15). It is
recomputed on read, pure, and time-anchored to the caller-supplied `now` (no
wall-clock inside) so results are reproducible (research-grade, ADR-0006).

How the number is built:
- Every present sub-measure is normalized to a common **0-100, higher = better**
  metric using a small, illustrative reference registry (physician-signed config
  pending validation). **Inversion is driven by the Phase-1 polarity registry**
  (`directionality.py`), never hardcoded per call — pain, numbness and HbA1c read
  higher = worse, so they are flipped during normalization.
- A **domain score** is the mean of its present sub-measures.
- The **composite** weights the *present* domains and renormalizes the weights
  across them (an absent domain is never imputed as 0 — that would fabricate a
  false alarm). With no domain present the score is `None`.
- The **30-day delta** fits each sub-measure's series the same deterministic way
  the engine fits a line, evaluates the composite at `as_of` and ~30 days prior,
  and gates the direction with a fixed absolute point floor on the bounded 0-100
  index (``MEANINGFUL_ABSOLUTE_POINTS``) so wobble is not called a trend — and,
  crucially, a real move is never masked just because the score is high. The
  composite's own delta is the single source of truth for direction — card colour
  and arrow are both driven by it, so they can never contradict (a real defect the
  ADR retires by removing the multi-signal vote from this surface).
- **Confidence (High/Medium/Low)** comes from domain coverage + data recency only.
  Adherence and BioMech daily completion never enter the score; stale data degrades
  Confidence and is flagged, so a stale Index is never dressed up as fresh.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, datetime

from app.schemas.trajectory import ConfidenceLevel, Direction
from app.trajectory.directionality import Polarity, polarity_for
from app.trajectory.points import ObservationPoint
from app.trajectory.stats import (
    MIN_POINTS,
    MIN_SPAN_DAYS,
    SECONDS_PER_DAY,
    least_squares_slope,
)

# Weights are LOCKED by the owner (ADR-0034 §1); symptom-forward on purpose.
DELTA_WINDOW_DAYS = 30.0

# The composite is a bounded 0-100 index, so its 30-day direction is gated by a FIXED
# ABSOLUTE point floor — NOT a relative-change / _series_scale test on the [now, prior]
# pair. A relative gate scales the "meaningful" bar with the current score's magnitude
# (~5% of the score), so the same real move reads as noise near 100 but a trend near 10 —
# masking a genuine decline for healthier patients, the exact harm ADR-0034 §3 warns
# against. A fixed floor is magnitude-independent and symmetric: a +N and a -N move of the
# same size classify identically at every baseline. A change of >= this many points on the
# 0-100 index is "meaningful"; below it the direction is steady. This is an **illustrative
# v1 threshold, pending clinical validation** (consistent with the ADR's honesty about its
# illustrative, physician-signed config). Only the DIRECTION classification uses the floor;
# the displayed `score_delta_30d` remains the true rounded composite delta.
MEANINGFUL_ABSOLUTE_POINTS = 3.0


class Domain(enum.StrEnum):
    """The three NSI domains, each carrying its locked weight (see ``DOMAIN_WEIGHTS``)."""

    symptoms = "symptoms"
    function = "function"
    physiologic = "physiologic"


DOMAIN_WEIGHTS: dict[Domain, float] = {
    Domain.symptoms: 0.45,
    Domain.function: 0.40,
    Domain.physiologic: 0.15,
}


# Domain-appropriate freshness windows (days). Symptoms are captured daily and go
# stale within days; HbA1c is a ~90-day integral and stays "fresh" far longer. These
# reuse the engine's freshness idea (FRESH_WITHIN_DAYS / STALE_AFTER_DAYS) per domain.
# Illustrative, physician-signed config pending validation.
_FRESH_WITHIN: dict[Domain, float] = {
    Domain.symptoms: 14.0,
    Domain.function: 30.0,
    Domain.physiologic: 120.0,
}
_STALE_AFTER: dict[Domain, float] = {
    Domain.symptoms: 30.0,
    Domain.function: 90.0,
    Domain.physiologic: 180.0,
}


@dataclass(frozen=True, slots=True)
class MeasureRef:
    """One sub-measure's domain + illustrative raw reference band.

    The band maps the raw value linearly onto 0-100 (higher raw -> higher, before
    polarity). Direction of "better" is NOT stored here — it is read from the
    Phase-1 polarity registry, so a single source governs inversion.

    Illustrative, physician-signed config pending validation (ADR-0034 §2).
    """

    domain: Domain
    lo: float  # raw value at the bottom of the band
    hi: float  # raw value at the top of the band


# The measure registry: which sub-measures feed the composite, their domain, and the
# raw band each is scaled against. Codes absent here (e.g. adl_daily_score, cadence)
# are reported by the engine but do not enter the Index — avoids double-counting the
# 0-12 daily roll-up against its own components, and skips unjudgeable measures.
_MEASURES: dict[str, MeasureRef] = {
    # --- Symptoms (0-10 severity items; higher = worse, inverted via polarity) ---
    "symptom_pain": MeasureRef(Domain.symptoms, 0.0, 10.0),
    "symptom_numbness": MeasureRef(Domain.symptoms, 0.0, 10.0),
    # --- Function (BioMech device-grade composite scores + self-reported ADLs) ---
    # Only the two headline BioMech scores (both 0-100, higher = better) enter the Index;
    # their component metrics (speed/movement/position, impact/support/pelvic) surface as
    # trajectory signals but are NOT summed here — that would double-count the same test
    # against its own parts (the rule that also excludes adl_daily_score). Real report
    # catalog per ADR-0036.
    "biomech_balance_score": MeasureRef(Domain.function, 0.0, 100.0),
    "biomech_gait_score": MeasureRef(Domain.function, 0.0, 100.0),
    "adl_walking": MeasureRef(Domain.function, 0.0, 4.0),
    "adl_stairs": MeasureRef(Domain.function, 0.0, 4.0),
    "adl_balance_confidence": MeasureRef(Domain.function, 0.0, 4.0),
    # --- Physiologic (HbA1c, ADA-informed illustrative band; higher = worse) ---
    "4548-4": MeasureRef(Domain.physiologic, 5.0, 10.0),
    "hba1c": MeasureRef(Domain.physiologic, 5.0, 10.0),
}


@dataclass(frozen=True, slots=True)
class NeuropathyStatusIndex:
    """The computed NSI, ready to drop onto the Trajectory contract."""

    score: int | None
    score_delta_30d: int | None
    as_of: date | None
    confidence_level: ConfidenceLevel | None
    direction: Direction | None  # improving | stable | declining | None
    data_is_stale: bool


def _normalize(code: str, value: float, ref: MeasureRef) -> float:
    """Map a raw value onto 0-100 (higher = better), inverting worse-is-higher measures.

    The band is scaled linearly and clamped; inversion is decided by the Phase-1
    polarity registry so the data — not this function — drives which way is better.
    """
    span = ref.hi - ref.lo
    frac = 0.0 if span == 0 else (value - ref.lo) / span
    frac = min(max(frac, 0.0), 1.0)
    scaled = frac * 100.0
    if polarity_for(code) is Polarity.lower_is_better:
        scaled = 100.0 - scaled
    return scaled


def _fit_now_and_prior(series: list[ObservationPoint]) -> tuple[float, float, datetime]:
    """A sub-measure's fitted value now and ~30 days prior, plus its newest timestamp.

    Fits the same least-squares line the engine uses. A series too thin or too short
    to judge a trend contributes its latest value flat (equal now/prior), so it counts
    toward the *level* but moves the *delta* by nothing — noise is never a trend.
    """
    ordered = sorted(series, key=lambda point: point.effective_at)
    first_at = ordered[0].effective_at
    latest_at = ordered[-1].effective_at
    span_days = (latest_at - first_at).total_seconds() / SECONDS_PER_DAY
    values = [point.value for point in ordered]
    latest_value = values[-1]

    if len(ordered) < MIN_POINTS or span_days < MIN_SPAN_DAYS:
        return latest_value, latest_value, latest_at

    xs = [(point.effective_at - first_at).total_seconds() / SECONDS_PER_DAY for point in ordered]
    slope = least_squares_slope(xs, values)
    mean_x = sum(xs) / len(xs)
    mean_y = sum(values) / len(values)
    value_now = mean_y + slope * (span_days - mean_x)
    value_prior = mean_y + slope * (span_days - DELTA_WINDOW_DAYS - mean_x)
    return value_now, value_prior, latest_at


def _composite(domain_values: dict[Domain, list[float]]) -> float | None:
    """Weight present domains and renormalize the weights across them.

    An absent domain is dropped from the weighting, never imputed as 0 — the number
    then *means* a partial view, which Confidence surfaces.
    """
    present = {d: vals for d, vals in domain_values.items() if vals}
    if not present:
        return None
    total_weight = sum(DOMAIN_WEIGHTS[d] for d in present)
    weighted = sum(DOMAIN_WEIGHTS[d] * (sum(vals) / len(vals)) for d, vals in present.items())
    return weighted / total_weight


def _confidence(
    present_domains: set[Domain], domain_age_days: dict[Domain, float]
) -> tuple[ConfidenceLevel, bool]:
    """High/Medium/Low from coverage + recency, plus whether the data reads stale.

    - High  = all three domains present and each within its freshness window.
    - Low   = only one domain, or a contributing domain is materially stale.
    - Medium= otherwise (two domains, or three with minor staleness).
    """
    n = len(present_domains)
    all_fresh = all(domain_age_days[d] <= _FRESH_WITHIN[d] for d in present_domains)
    material_stale = any(domain_age_days[d] > _STALE_AFTER[d] for d in present_domains)

    if material_stale or n == 1:
        level = ConfidenceLevel.low
    elif n == 3 and all_fresh:
        level = ConfidenceLevel.high
    else:
        level = ConfidenceLevel.medium
    return level, material_stale


def compute_index(
    series_by_code: dict[str, list[ObservationPoint]], now: datetime
) -> NeuropathyStatusIndex:
    """Compute the NSI over per-code analyzable series (already integrity-filtered).

    Deterministic in (series, now). Returns an all-``None`` index (score None) when
    no domain has a contributing measure.
    """
    now_values: dict[Domain, list[float]] = {d: [] for d in Domain}
    prior_values: dict[Domain, list[float]] = {d: [] for d in Domain}
    domain_latest: dict[Domain, datetime] = {}

    for code, series in series_by_code.items():
        ref = _MEASURES.get(code.lower())
        if ref is None or not series:
            continue
        value_now, value_prior, latest_at = _fit_now_and_prior(series)
        now_values[ref.domain].append(_normalize(code, value_now, ref))
        prior_values[ref.domain].append(_normalize(code, value_prior, ref))
        prior = domain_latest.get(ref.domain)
        if prior is None or latest_at > prior:
            domain_latest[ref.domain] = latest_at

    composite_now = _composite(now_values)
    if composite_now is None:
        return NeuropathyStatusIndex(None, None, None, None, None, False)

    composite_prior = _composite(prior_values)
    assert composite_prior is not None  # same present domains as composite_now (narrowing)
    raw_delta = composite_now - composite_prior
    # Gate the direction with a FIXED absolute point floor on the bounded 0-100 index, so
    # a genuine decline is never masked at a high baseline (nor a wobble called a trend at
    # a low one). Symmetric in sign and independent of the current score's magnitude. The
    # displayed integer stays the TRUE rounded delta; only the direction uses the floor.
    # A meaningful move is >= 3 points, so its rounded value is never 0 — arrow, colour,
    # and word always agree in sign.
    delta = 0 if abs(raw_delta) < MEANINGFUL_ABSOLUTE_POINTS else round(raw_delta)

    direction = (
        Direction.improving if delta > 0 else Direction.declining if delta < 0 else Direction.stable
    )

    as_of_dt = max(domain_latest.values())
    present_domains = set(domain_latest)
    domain_age_days = {
        d: (now - latest).total_seconds() / SECONDS_PER_DAY for d, latest in domain_latest.items()
    }
    confidence_level, data_is_stale = _confidence(present_domains, domain_age_days)

    return NeuropathyStatusIndex(
        score=round(composite_now),
        score_delta_30d=delta,
        as_of=as_of_dt.date(),
        confidence_level=confidence_level,
        direction=direction,
        data_is_stale=data_is_stale,
    )
