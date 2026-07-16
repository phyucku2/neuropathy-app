"""Tests for the Neuropathy Status Index — the deterministic 0-100 composite (ADR-0034).

These lock the honest behavior of the NSI: a symptom-forward weighted composite,
per-measure normalization with data-driven inversion (rising pain LOWERS the score),
missing-domain renormalization (never impute an absent domain as 0), a composite-own
30-day delta that is the single source of truth for direction, Confidence from coverage
+ recency only, an honest `as_of`, and `None` when nothing is present. All data is
synthetic; `now` is always passed explicitly so every case is reproducible.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.schemas.trajectory import ConfidenceLevel, Direction
from app.trajectory.composite import compute_index
from app.trajectory.points import ObservationPoint
from app.trajectory.stats import series_by_code

NOW = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


def _pt(code: str, value: float, days_ago: float, source: str = "lab") -> ObservationPoint:
    return ObservationPoint(
        code=code,
        source=source,
        value=value,
        effective_at=NOW - timedelta(days=days_ago),
        status="final",
    )


def _series(
    code: str,
    values: list[float],
    *,
    source: str = "lab",
    newest_days_ago: float = 5,
    step_days: float = 10,
) -> list[ObservationPoint]:
    oldest = newest_days_ago + step_days * (len(values) - 1)
    return [_pt(code, value, oldest - i * step_days, source) for i, value in enumerate(values)]


def _index(points: list[ObservationPoint]):  # noqa: ANN202 - test helper
    return compute_index(series_by_code(points), NOW)


# Reusable flat, fresh, full-coverage series (score 72; see test below).
def _full_three_domain() -> list[ObservationPoint]:
    return (
        _series("symptom_pain", [2, 2, 2, 2], source="adl")
        + _series("symptom_numbness", [3, 3, 3, 3], source="adl")
        + _series("biomech_balance_score", [70, 70, 70, 70], source="biomech")
        + _series("biomech_gait_speed", [1.2, 1.2, 1.2, 1.2], source="biomech")
        + _series("adl_walking", [3, 3, 3, 3], source="adl")
        + _series("adl_stairs", [3, 3, 3, 3], source="adl")
        + _series("adl_balance_confidence", [3, 3, 3, 3], source="adl")
        + _series("4548-4", [7.0, 7.0, 7.0, 7.0])
    )


# ---------------------------------------------------------------------------
# The composite on a full three-domain case — exact ints
# ---------------------------------------------------------------------------


def test_full_three_domain_composite_is_the_weighted_mean() -> None:
    # Symptoms mean(80,70)=75; Function mean(70,75,75,75,75)=74; Physiologic 60.
    # 0.45*75 + 0.40*74 + 0.15*60 = 72.35 -> 72.
    index = _index(_full_three_domain())

    assert index.score == 72
    assert index.score_delta_30d == 0  # every series is flat
    assert index.direction is Direction.stable
    assert index.confidence_level is ConfidenceLevel.high
    assert index.data_is_stale is False


# ---------------------------------------------------------------------------
# Missing-domain renormalization — weights spread over PRESENT domains
# ---------------------------------------------------------------------------


def test_absent_symptom_domain_renormalizes_the_weights() -> None:
    # Function 74 + Physiologic 60 only (symptom domain toggled off / absent):
    # weights renormalized over {0.40, 0.15} -> (0.40*74 + 0.15*60)/0.55 = 70.18 -> 70.
    # It must NOT impute symptoms as 0 (that would fabricate a false alarm, dragging
    # the number far below 70).
    points = (
        _series("biomech_balance_score", [70, 70, 70, 70], source="biomech")
        + _series("biomech_gait_speed", [1.2, 1.2, 1.2, 1.2], source="biomech")
        + _series("adl_walking", [3, 3, 3, 3], source="adl")
        + _series("adl_stairs", [3, 3, 3, 3], source="adl")
        + _series("adl_balance_confidence", [3, 3, 3, 3], source="adl")
        + _series("4548-4", [7.0, 7.0, 7.0, 7.0])
    )
    index = _index(points)

    assert index.score == 70
    # Two domains present, both fresh -> Medium (not High: coverage is partial).
    assert index.confidence_level is ConfidenceLevel.medium


def test_no_data_yields_a_none_score() -> None:
    index = _index([])

    assert index.score is None
    assert index.score_delta_30d is None
    assert index.as_of is None
    assert index.confidence_level is None
    assert index.direction is None
    assert index.data_is_stale is False


# ---------------------------------------------------------------------------
# Inverted polarity: rising pain LOWERS the score (data-driven inversion)
# ---------------------------------------------------------------------------


def test_rising_pain_lowers_the_score_and_reads_declining() -> None:
    # Pain climbing 1->4 while everything else is flat: the symptom domain falls, so
    # the composite's own 30-day delta is negative and the direction is declining.
    points = (
        _series("symptom_pain", [1, 2, 3, 4], source="adl")
        + _series("symptom_numbness", [3, 3, 3, 3], source="adl")
        + _series("biomech_balance_score", [70, 70, 70, 70], source="biomech")
        + _series("4548-4", [7.0, 7.0, 7.0, 7.0])
    )
    index = _index(points)

    assert index.score == 66
    assert index.score_delta_30d is not None and index.score_delta_30d < 0
    assert index.direction is Direction.declining


def test_rising_balance_raises_the_score_and_reads_improving() -> None:
    points = (
        _series("biomech_balance_score", [55, 60, 65, 72], source="biomech")
        + _series("symptom_pain", [2, 2, 2, 2], source="adl")
        + _series("symptom_numbness", [2, 2, 2, 2], source="adl")
        + _series("4548-4", [7.0, 7.0, 7.0, 7.0])
    )
    index = _index(points)

    assert index.score_delta_30d is not None and index.score_delta_30d > 0
    assert index.direction is Direction.improving
    # The arrow (delta sign) and the direction word can never contradict.
    assert (index.score_delta_30d > 0) == (index.direction is Direction.improving)


# ---------------------------------------------------------------------------
# Direction is gated by a FIXED absolute point floor on the 0-100 index — NOT a
# relative-change test that scales with the score's magnitude. A ~5-point move must
# classify the SAME at a high baseline as at a low one (never masked when healthy).
# ---------------------------------------------------------------------------


def _one_domain_at(now_value: float, prior_value: float) -> list[ObservationPoint]:
    """A single-measure balance series whose fitted composite moves now<-prior.

    Balance is a 0-100, higher-is-better function measure, so the one-domain composite
    equals the balance value: a clean lever to place the composite at any 30-day endpoints.
    A 4-point straight line over ~30 days makes now/prior the exact endpoints.
    """
    return _series(
        "biomech_balance_score",
        [
            prior_value,
            prior_value + (now_value - prior_value) / 3,
            now_value - (now_value - prior_value) / 3,
            now_value,
        ],
        source="biomech",
        newest_days_ago=0,
        step_days=10,
    )


def test_five_point_decline_at_high_baseline_reads_declining_not_masked() -> None:
    # The reviewer's probe: a genuine ~5-point decline near the top of the scale. A
    # relative gate (~5% of ~95 = ~4.75) would swallow this and render stable/0 — the
    # exact "mask a decline for healthier patients" harm ADR-0034 §3 warns against.
    index = _index(_one_domain_at(now_value=95.0, prior_value=100.0))

    assert index.score_delta_30d is not None and index.score_delta_30d < 0
    assert index.direction is Direction.declining


def test_five_point_decline_at_low_baseline_also_reads_declining() -> None:
    # The SAME 5-point move at a low baseline — magnitude-independent, so also declining.
    index = _index(_one_domain_at(now_value=15.0, prior_value=20.0))

    assert index.score_delta_30d is not None and index.score_delta_30d < 0
    assert index.direction is Direction.declining


def test_five_point_rise_at_high_baseline_reads_improving() -> None:
    index = _index(_one_domain_at(now_value=95.0, prior_value=90.0))

    assert index.score_delta_30d is not None and index.score_delta_30d > 0
    assert index.direction is Direction.improving


def test_sub_threshold_wobble_reads_steady_at_high_and_low_baselines() -> None:
    # A ~1-2 point wobble is below the fixed floor at BOTH baselines -> steady, delta 0.
    for now_value, prior_value in ((98.0, 100.0), (10.0, 12.0), (99.0, 100.0), (11.0, 10.0)):
        index = _index(_one_domain_at(now_value=now_value, prior_value=prior_value))
        assert index.score_delta_30d == 0, (now_value, prior_value)
        assert index.direction is Direction.stable, (now_value, prior_value)


def test_direction_is_magnitude_independent_symmetric() -> None:
    # A +5 and a -5 move of equal size classify with equal magnitude / opposite sign,
    # at any baseline — the floor is symmetric and does not scale with the score.
    up = _index(_one_domain_at(now_value=100.0, prior_value=95.0))
    down = _index(_one_domain_at(now_value=95.0, prior_value=100.0))
    assert up.score_delta_30d is not None and down.score_delta_30d is not None
    assert up.score_delta_30d == -down.score_delta_30d
    assert up.direction is Direction.improving
    assert down.direction is Direction.declining


# ---------------------------------------------------------------------------
# Confidence: coverage + recency only (never adherence/health)
# ---------------------------------------------------------------------------


def test_confidence_high_needs_all_three_fresh_domains() -> None:
    assert _index(_full_three_domain()).confidence_level is ConfidenceLevel.high


def test_confidence_medium_for_two_fresh_domains() -> None:
    points = _series("biomech_balance_score", [70, 70, 70, 70], source="biomech") + _series(
        "4548-4", [7.0, 7.0, 7.0, 7.0]
    )
    assert _index(points).confidence_level is ConfidenceLevel.medium


def test_confidence_low_for_a_single_domain() -> None:
    points = _series("biomech_balance_score", [70, 70, 70, 70], source="biomech")
    index = _index(points)

    assert index.score is not None  # a one-domain score still renders (renormalized)
    assert index.confidence_level is ConfidenceLevel.low


def test_stale_contributing_domain_degrades_confidence_and_flags_old_data() -> None:
    # Symptoms newest reading is 60 days old (> the 30-day symptom stale window), even
    # though function/physiologic are fresh: Confidence drops to Low and data reads old.
    points = (
        _series("symptom_pain", [2, 2, 2, 2], source="adl", newest_days_ago=60)
        + _series("symptom_numbness", [3, 3, 3, 3], source="adl", newest_days_ago=60)
        + _series("biomech_balance_score", [70, 70, 70, 70], source="biomech")
        + _series("4548-4", [7.0, 7.0, 7.0, 7.0])
    )
    index = _index(points)

    assert index.confidence_level is ConfidenceLevel.low
    assert index.data_is_stale is True


# ---------------------------------------------------------------------------
# `as_of` = the newest contributing observation's effective date
# ---------------------------------------------------------------------------


def test_as_of_is_the_newest_contributing_effective_date() -> None:
    # Newest contributing reading is the balance point 3 days ago -> Jul 9.
    points = (
        _series("biomech_balance_score", [70, 70, 70, 70], source="biomech", newest_days_ago=3)
        + _series("4548-4", [7.0, 7.0, 7.0, 7.0], newest_days_ago=20)
        + _series("symptom_pain", [2, 2, 2, 2], source="adl", newest_days_ago=10)
        + _series("symptom_numbness", [2, 2, 2, 2], source="adl", newest_days_ago=10)
    )
    index = _index(points)

    assert index.as_of == date(2026, 7, 9)


def test_non_registry_codes_do_not_enter_the_index() -> None:
    # adl_daily_score (the 0-12 roll-up) and unknown codes are reported by the engine
    # but must NOT contribute to the composite (no double counting, no unjudged guess).
    points = (
        _series("biomech_balance_score", [70, 70, 70, 70], source="biomech")
        + _series("adl_daily_score", [9, 9, 9, 9], source="adl")
        + _series("mystery_metric", [1, 2, 3, 4], source="adl")
    )
    index = _index(points)

    # Only the function domain (balance = 70) is present -> score 70, Low confidence.
    assert index.score == 70
    assert index.confidence_level is ConfidenceLevel.low


def test_index_is_deterministic_regardless_of_point_order() -> None:
    points = _full_three_domain()
    assert _index(list(points)) == _index(list(reversed(points)))
