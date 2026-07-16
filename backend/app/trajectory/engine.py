"""The trajectory engine — deterministic, explainable, honest (ADR-0003, Brainstorm #3).

`compute_trajectory` turns analyzable observation points into the locked `Trajectory`
contract. Every number is computed in code; the plain-language summary is assembled
from templates over those computed facts — no model calls, nothing unsourced.

Design commitments:
- Per-signal judgments come from `directionality` (unknown codes are reported, not
  judged — no silent clinical claims).
- The overall call is a weighted vote of judged signals; ties resolve toward
  `declining` (clinically conservative — better to prompt a look than to reassure).
- Confidence is bounded and grows with evidence: more judged signals, fresher data,
  and longer coverage never lower it.
- `insufficient_data` is a first-class outcome, and `data_gaps` says exactly what
  is missing, stale, or unjudgeable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.models.observation import ObservationStatus, SourceType
from app.schemas.trajectory import Direction, SignalTrend, Trajectory
from app.services.observation import counts_toward_analysis
from app.trajectory.composite import compute_index
from app.trajectory.directionality import Polarity, SignalInfo, signal_info
from app.trajectory.points import ObservationPoint
from app.trajectory.stats import (
    MIN_POINTS,
    SECONDS_PER_DAY,
    Movement,
    RangePosition,
    SeriesStats,
    compute_series_stats,
    latest_range_position,
    series_by_code,
)

# A signal whose newest reading is older than this no longer reflects "now"; it is
# flagged as a gap and drags confidence down via the recency factor.
STALE_AFTER_DAYS = 90.0

# Data newer than this gets full recency credit; older data decays linearly.
FRESH_WITHIN_DAYS = 30.0

# Evidence levels at which each confidence factor saturates.
_FULL_JUDGED_SIGNALS = 3
_FULL_COVERAGE_DAYS = 90.0
_FULL_RICHNESS_POINTS = 6

# Confidence bounds: never certain, never zero once something was judged.
_CONFIDENCE_CEILING = 0.95
_CONFIDENCE_FLOOR = 0.1
_INSUFFICIENT_CONFIDENCE = 0.05

# Conservative tie-break: when vote weights tie exactly, the less rosy call wins.
_TIE_PRIORITY = {Direction.declining: 2, Direction.stable: 1, Direction.improving: 0}

_SOURCE_GAP_MESSAGES = {
    SourceType.lab: "No lab results yet.",
    SourceType.adl: "No daily-activity check-ins yet.",
    SourceType.biomech: "No BioMech reports yet.",
}

_RANGE_NOTES = {
    RangePosition.below: "below the typical range",
    RangePosition.within: "in the typical range",
    RangePosition.above: "above the typical range",
}


@dataclass(frozen=True, slots=True)
class _Assessment:
    """One signal's computed facts plus its (possibly withheld) judgment."""

    code: str
    source: str
    info: SignalInfo
    stats: SeriesStats
    range_position: RangePosition | None
    direction: Direction
    judged: bool  # True when the signal votes on the overall direction
    weight: float
    detail: str


def _days_between(earlier: datetime, later: datetime) -> float:
    return (later - earlier).total_seconds() / SECONDS_PER_DAY


def _judge(
    polarity: Polarity, movement: Movement, range_position: RangePosition | None
) -> tuple[Direction, bool]:
    """Map a series' raw movement to better/worse via the signal's polarity.

    Returns (direction, judged). Unjudged signals — unknown polarity, or
    in-range-is-better with no reference range on file — report their movement in
    the detail text but carry `insufficient_data` and never vote.
    """
    if movement is Movement.insufficient:
        return Direction.insufficient_data, False
    if polarity is Polarity.higher_is_better:
        by_movement = {
            Movement.rising: Direction.improving,
            Movement.falling: Direction.declining,
            Movement.flat: Direction.stable,
        }
        return by_movement[movement], True
    if polarity is Polarity.lower_is_better:
        by_movement = {
            Movement.rising: Direction.declining,
            Movement.falling: Direction.improving,
            Movement.flat: Direction.stable,
        }
        return by_movement[movement], True
    if polarity is Polarity.in_range_is_better and range_position is not None:
        if movement is Movement.flat or range_position is RangePosition.within:
            # Flat, or drifting while still inside the normal range: steady.
            return Direction.stable, True
        toward_range = (range_position is RangePosition.below) == (movement is Movement.rising)
        return (Direction.improving if toward_range else Direction.declining), True
    return Direction.insufficient_data, False


def _weight(stats: SeriesStats, now: datetime) -> float:
    """A judged signal's vote weight: richer and fresher series count for more."""
    richness = min(stats.n_points / _FULL_RICHNESS_POINTS, 1.0)
    age_days = _days_between(stats.latest_at, now)
    recency = (
        1.0
        if age_days <= FRESH_WITHIN_DAYS
        else (max(0.25, 1.0 - (age_days - FRESH_WITHIN_DAYS) / 365.0))
    )
    return richness * recency


def _format_amount(value: float) -> str:
    return f"{round(value, 2):g}"


def _detail(info: SignalInfo, stats: SeriesStats, range_position: RangePosition | None) -> str:
    """Plain-language, computed-from-data detail, e.g. 'balance up 8 over 30 days'."""
    days = max(round(stats.span_days), 1)
    if stats.movement is Movement.insufficient:
        readings = "reading" if stats.n_points == 1 else "readings"
        text = f"{info.label}: only {stats.n_points} {readings} over {days} days"
    elif stats.movement is Movement.flat:
        text = f"{info.label} steady over {days} days"
    else:
        word = "up" if stats.movement is Movement.rising else "down"
        text = f"{info.label} {word} {_format_amount(abs(stats.fitted_change))} over {days} days"
    if range_position is not None:
        text += f" ({_RANGE_NOTES[range_position]})"
    return text


def _assess(code: str, series: list[ObservationPoint], now: datetime) -> _Assessment:
    info = signal_info(code)
    stats = compute_series_stats(series)
    range_position = latest_range_position(series)
    direction, judged = _judge(info.polarity, stats.movement, range_position)
    return _Assessment(
        code=code,
        source=series[-1].source,
        info=info,
        stats=stats,
        range_position=range_position,
        direction=direction,
        judged=judged,
        weight=_weight(stats, now) if judged else 0.0,
        detail=_detail(info, stats, range_position),
    )


def _overall_direction(judged: list[_Assessment]) -> Direction:
    """Weighted vote over judged signals; exact ties resolve conservatively."""
    if not judged:
        return Direction.insufficient_data
    scores = {Direction.improving: 0.0, Direction.stable: 0.0, Direction.declining: 0.0}
    for assessment in judged:
        scores[assessment.direction] += assessment.weight
    return max(scores, key=lambda direction: (scores[direction], _TIE_PRIORITY[direction]))


def _confidence(judged: list[_Assessment], now: datetime) -> float:
    """Bounded confidence that grows (never shrinks) with evidence.

    Three factors, each in (0, 1]: how many signals were judged, how fresh the
    newest judged data is, and how long a window the richest series covers. Adding
    data can only raise each factor, so confidence is monotone in evidence.
    """
    if not judged:
        return _INSUFFICIENT_CONFIDENCE
    count_factor = min(len(judged) / _FULL_JUDGED_SIGNALS, 1.0)
    newest = max(assessment.stats.latest_at for assessment in judged)
    age_days = _days_between(newest, now)
    recency = (
        1.0
        if age_days <= FRESH_WITHIN_DAYS
        else (max(0.3, 1.0 - (age_days - FRESH_WITHIN_DAYS) / 365.0))
    )
    longest_span = max(assessment.stats.span_days for assessment in judged)
    coverage = 0.4 + 0.6 * min(longest_span / _FULL_COVERAGE_DAYS, 1.0)
    raw = _CONFIDENCE_CEILING * count_factor * recency * coverage
    return round(min(max(raw, _CONFIDENCE_FLOOR), _CONFIDENCE_CEILING), 2)


def _data_gaps(assessments: list[_Assessment], now: datetime) -> list[str]:
    """Everything that limits the answer, named plainly: absent sources, thin or
    unjudgeable signals, and stale data."""
    gaps: list[str] = []
    present_sources = {assessment.source for assessment in assessments}
    for source in SourceType:
        if source.value not in present_sources:
            gaps.append(_SOURCE_GAP_MESSAGES.get(source, f"No {source.value} data yet."))
    for assessment in assessments:
        label = assessment.info.label
        stats = assessment.stats
        if stats.movement is Movement.insufficient:
            gaps.append(
                f"Not enough {label} readings to judge a trend"
                f" (need at least {MIN_POINTS} over 2 or more weeks)."
            )
        elif not assessment.judged:
            if assessment.info.polarity is Polarity.unknown:
                gaps.append(
                    f"We show the {label} trend but do not judge it"
                    " — we don't yet know which direction is better."
                )
            else:
                gaps.append(f"No reference range on file for {label}, so it is not judged.")
        if (
            assessment.judged
            and assessment.range_position is not None
            and assessment.range_position is not RangePosition.within
        ):
            note = _RANGE_NOTES[assessment.range_position]
            gaps.append(f"{_capitalize(label)} is {note} — worth discussing with your care team.")
        age_days = _days_between(stats.latest_at, now)
        if age_days > STALE_AFTER_DAYS:
            gaps.append(f"The last {label} reading was {round(age_days)} days ago.")
    return gaps


def _capitalize(text: str) -> str:
    return text[0].upper() + text[1:]


def _join(labels: list[str]) -> str:
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _labels_for(judged: list[_Assessment], direction: Direction) -> list[str]:
    """Deduped plain-language labels of judged signals in a direction, heaviest first."""
    matching = sorted(
        (a for a in judged if a.direction is direction),
        key=lambda a: (-a.weight, a.info.label),
    )
    labels: list[str] = []
    for assessment in matching:
        if assessment.info.label not in labels:
            labels.append(assessment.info.label)
    return labels


def _summary(direction: Direction, judged: list[_Assessment]) -> str:
    """Template-based plain language (6th-8th grade): names the drivers by their
    friendly labels, never a code; constructive, never alarmist."""
    if direction is Direction.insufficient_data:
        return "There isn't enough data yet to see a clear trend. More readings will help."

    improving = _labels_for(judged, Direction.improving)
    declining = _labels_for(judged, Direction.declining)
    steady = _labels_for(judged, Direction.stable)

    sentences: list[str] = []
    if direction is Direction.improving:
        verb = "is" if len(improving) == 1 else "are"
        sentences.append(f"{_capitalize(_join(improving))} {verb} looking better.")
        if declining:
            sentences.append(f"One thing is worth a look: {_join(declining)}.")
    elif direction is Direction.declining:
        verb = "has" if len(declining) == 1 else "have"
        sentences.append(f"{_capitalize(_join(declining))} {verb} been slipping lately.")
        sentences.append("This is a good thing to talk over with your care team.")
        if improving:
            verb = "is" if len(improving) == 1 else "are"
            sentences.append(f"On the bright side, {_join(improving)} {verb} looking better.")
    else:
        verb = "is" if len(steady) == 1 else "are"
        sentences.append(f"{_capitalize(_join(steady))} {verb} holding steady.")
        if declining:
            sentences.append(f"One thing is worth a look: {_join(declining)}.")
    return " ".join(sentences)


def _analyzable(points: list[ObservationPoint]) -> list[ObservationPoint]:
    """Defense in depth: re-apply the integrity filter even on pre-built points."""
    kept: list[ObservationPoint] = []
    for point in points:
        try:
            status = ObservationStatus(point.status)
        except ValueError:
            continue  # unrecognized status: never silently analyzed
        if counts_toward_analysis(status):
            kept.append(point)
    return kept


def compute_trajectory(points: list[ObservationPoint], now: datetime) -> Trajectory:
    """Compute the explainable health trajectory for one patient's points.

    Deterministic: same points + same `now` always yield the same Trajectory.
    `now` is passed explicitly so results are reproducible (research-grade, ADR-0006).
    """
    series = series_by_code(_analyzable(points))
    assessments = [_assess(code, series[code], now) for code in sorted(series)]
    judged = [assessment for assessment in assessments if assessment.judged]

    # The Neuropathy Status Index (ADR-0034): the composite is the SINGLE SOURCE OF
    # TRUTH for the hero card's direction — its own 30-day delta, never the per-signal
    # vote below (which still drives the "what's driving it" list + summary).
    index = compute_index(series, now)

    direction = _overall_direction(judged)
    return Trajectory(
        direction=direction,
        confidence=_confidence(judged, now),
        summary=_summary(direction, judged),
        signals=[
            SignalTrend(
                code=assessment.code,
                source=assessment.source,
                direction=assessment.direction,
                detail=assessment.detail,
            )
            for assessment in assessments
        ],
        data_gaps=_data_gaps(assessments, now),
        score=index.score,
        score_delta_30d=index.score_delta_30d,
        as_of=index.as_of,
        confidence_level=index.confidence_level,
        direction_word=index.direction,
        data_is_stale=index.data_is_stale,
    )
