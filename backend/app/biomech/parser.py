"""Parse extracted BioMech report text into a typed, closed-set report (ADR-0014; real
report format per ADR-0036).

BioMech's real Balance and Gait test reports are exported as PDFs whose text layer, when
extracted with pypdf, emits each field on its **own line** — label, then unit, then value —
with bold rows (composite scores, "% Normal" rows) **duplicated**. There are no
`label: value` rows; the only colons are in the header (`Patient:`, `Test ID:`). This
module normalizes that stream and reads it closed-set:

- **Collapse adjacent duplicate lines**, which removes the bold-row duplication and turns
  each metric into a clean ``label → unit → value → [range]`` sequence.
- **Closed metric registry (METRICS).** Only the codes V1 understands are captured; each has
  a curated display, unit, valid range, polarity, and the exact report label(s) it maps to.
  Unknown lines are ignored — document free text NEVER becomes a display or a code (injection
  posture, ADR-0011).
- **Never crash, never fabricate.** A non-numeric value (e.g. "N/A"), a split value
  ("47 / 53"), or an out-of-range number is skipped with a per-metric warning; the value is
  never coerced or invented. Empty or unrecognizable text yields a report with zero metrics
  and warnings, not an exception.

The route turns the returned report into research-grade Observations (app/biomech/ingest.py);
this module is pure (no I/O), so it is fully unit-testable.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from datetime import UTC, datetime


class ReportKind(enum.StrEnum):
    """The two report kinds BioMech's portal exports and V1 understands."""

    balance = "balance"
    gait = "gait"


@dataclass(frozen=True, slots=True)
class MetricSpec:
    """One metric V1 understands: its code, curated display/unit, valid range, and
    polarity. `higher_is_better` is True/False for judged metrics, None when direction
    carries no clear better/worse (mirrored in app/trajectory/directionality.py). `labels`
    are the exact (normalized) report labels that map to this metric, and `units` are the
    accepted unit tokens that must follow the label (a guard against mis-alignment)."""

    code: str
    display: str
    unit: str
    min_value: float
    max_value: float
    higher_is_better: bool | None
    labels: tuple[str, ...]
    units: tuple[str, ...]


# The closed set of metrics V1 ingests, keyed to the REAL report labels. Balance-report
# metrics first, then gait. The "% Normal" rows are population-referenced 0–100 values
# (higher = better) and are the cleanest inputs for the composite; the composite scores head
# each report. Ranges are generous bounds whose job is to reject nonsense, not judge.
METRICS: tuple[MetricSpec, ...] = (
    # --- Balance report ---
    MetricSpec(
        code="biomech_balance_score",
        display="Balance score",
        unit="%",
        min_value=0.0,
        max_value=100.0,
        higher_is_better=True,
        labels=("balance score",),
        units=("percent",),
    ),
    MetricSpec(
        code="biomech_balance_speed_normal",
        display="Balance speed (normalized)",
        unit="%",
        min_value=0.0,
        max_value=100.0,
        higher_is_better=True,
        labels=("average speed % normal",),
        units=("percent",),
    ),
    MetricSpec(
        code="biomech_balance_movement_normal",
        display="Balance movement (normalized)",
        unit="%",
        min_value=0.0,
        max_value=100.0,
        higher_is_better=True,
        labels=("average movement % normal",),
        units=("percent",),
    ),
    MetricSpec(
        code="biomech_balance_position_normal",
        display="Balance position (normalized)",
        unit="%",
        min_value=0.0,
        max_value=100.0,
        higher_is_better=True,
        labels=("average position % normal",),
        units=("percent",),
    ),
    # --- Gait report ---
    MetricSpec(
        code="biomech_gait_score",
        display="Gait score",
        unit="%",
        min_value=0.0,
        max_value=100.0,
        higher_is_better=True,
        labels=("gait score",),
        units=("percent",),
    ),
    MetricSpec(
        code="biomech_cadence",
        display="Cadence",
        unit="{steps}/min",
        min_value=0.0,
        max_value=400.0,
        higher_is_better=None,
        labels=("cadence",),
        units=("steps / min", "steps/min"),
    ),
    MetricSpec(
        code="biomech_step_length",
        display="Step length",
        unit="[ft_i]",
        min_value=0.0,
        max_value=10.0,
        higher_is_better=True,
        labels=("average step length",),
        units=("feet",),
    ),
    MetricSpec(
        code="biomech_total_steps",
        display="Total steps",
        unit="{steps}",
        min_value=0.0,
        max_value=100000.0,
        higher_is_better=None,
        labels=("total steps",),
        units=("steps",),
    ),
    MetricSpec(
        code="biomech_impact_symmetry",
        display="Impact symmetry",
        unit="%",
        min_value=0.0,
        max_value=100.0,
        higher_is_better=True,
        labels=("impact symmetry (left / right) % normal",),
        units=("percent",),
    ),
    MetricSpec(
        code="biomech_support_ratio",
        display="Support ratio",
        unit="%",
        min_value=0.0,
        max_value=100.0,
        higher_is_better=True,
        labels=("support ratio % normal (single:double)",),
        units=("percent",),
    ),
    MetricSpec(
        code="biomech_single_support_symmetry",
        display="Single-support symmetry",
        unit="%",
        min_value=0.0,
        max_value=100.0,
        higher_is_better=True,
        labels=("single support symmetry (left / right) % normal",),
        units=("percent",),
    ),
    MetricSpec(
        code="biomech_pelvic_tilt_neutral",
        display="Pelvic tilt (neutral)",
        unit="%",
        min_value=0.0,
        max_value=100.0,
        higher_is_better=True,
        labels=("pelvic tilt % neutral",),
        units=("percent",),
    ),
)

_SPEC_BY_LABEL: dict[str, MetricSpec] = {label: spec for spec in METRICS for label in spec.labels}
_KNOWN_UNITS: frozenset[str] = frozenset(unit for spec in METRICS for unit in spec.units)

# The header label whose following line carries the assessment date, and the sensor line.
_DATE_LABEL = "date of service:"
_DATE_FORMATS = ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d")

# Balance-condition tokens (stance / vision) — collected into a protocol string stored as
# provenance. Neuropathy-relevant: the eyes-open vs eyes-closed contrast is a proprioceptive
# signal (ADR-0036 notes it as a future sub-signal); here we simply preserve the condition.
_CONDITION_TOKENS = ("parallel", "tandem", "eyes open", "eyes closed", "feet together")

# A value must be a clean number, optionally with a trailing direction tag like "4.1 (RF)".
# Splits ("47 / 53"), "N/A", ranges, and units are NOT values and are skipped.
_VALUE = re.compile(r"^([-+]?\d+(?:\.\d+)?)(?:\s*\([A-Za-z ]+\))?$")
_MAX_DEVICE_LEN = 120


@dataclass(frozen=True, slots=True)
class BiomechMetric:
    """One accepted measurement: a registry code + its curated display/unit and value."""

    code: str
    display: str
    unit: str
    value: float


@dataclass(frozen=True, slots=True)
class BiomechReport:
    """A parsed BioMech report. `kind`/`assessment_at` are None when the text did not carry
    a recognizable marker (a warning explains); `metrics` holds only accepted, in-range
    measurements; `condition` is the balance protocol string when present; `warnings` lists
    every defensive skip for the uploader."""

    kind: ReportKind | None
    assessment_at: datetime | None
    device: str | None
    condition: str | None
    metrics: tuple[BiomechMetric, ...]
    warnings: tuple[str, ...]


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _dedup_adjacent(lines: list[str]) -> list[str]:
    """Strip blanks and collapse adjacent identical lines — this removes the bold-row
    duplication pypdf emits, turning each metric into `label → unit → value → [range]`."""
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if out and out[-1] == line:
            continue
        out.append(line)
    return out


def _parse_date(raw: str) -> datetime | None:
    """Parse a Date-of-Service value; naive dates are assumed UTC midnight (like labs), so
    every report's assessment_at is tz-aware and trend math never mixes naive/aware."""
    text = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _detect_kind(deduped: list[str]) -> ReportKind | None:
    for line in deduped:
        low = line.lower()
        if "balance individual test report" in low:
            return ReportKind.balance
        if "gait individual test report" in low:
            return ReportKind.gait
    return None


def _detect_condition(deduped: list[str]) -> str | None:
    parts = [
        line.rstrip(",") for line in deduped if any(t in line.lower() for t in _CONDITION_TOKENS)
    ]
    if not parts:
        return None
    # De-dupe while preserving order; cap length so a runaway line cannot bloat provenance.
    seen: list[str] = []
    for part in parts:
        if part not in seen:
            seen.append(part)
    return ", ".join(seen)[:_MAX_DEVICE_LEN]


def _metric_value(raw: str) -> float | None:
    """The clean numeric value of a value line, or None (skip, never guess). "97" -> 97.0;
    "4.1 (RF)" -> 4.1; "N/A", "47 / 53", "2.1 - 2.5 ft" -> None."""
    match = _VALUE.match(raw.strip())
    return float(match.group(1)) if match else None


def parse_report(text: str) -> BiomechReport:
    """Parse extracted report text into a typed BiomechReport (never raises).

    Collapses adjacent duplicate lines, detects the report kind / date / balance condition,
    then walks the normalized lines: when a line is a known metric label, the next line must
    be that metric's unit and the line after is its value (skipped with a warning when
    non-numeric, out of range, mis-unit, or a repeated code). Every other line is ignored.
    Missing kind or date is reported as a warning, not an error.
    """
    deduped = _dedup_adjacent(text.splitlines())
    metrics: list[BiomechMetric] = []
    warnings: list[str] = []
    seen_codes: set[str] = set()
    assessment_at: datetime | None = None

    for index, line in enumerate(deduped):
        low = _normalize(line)

        if low == _DATE_LABEL and assessment_at is None and index + 1 < len(deduped):
            assessment_at = _parse_date(deduped[index + 1])
            continue

        spec = _SPEC_BY_LABEL.get(low)
        if spec is None:
            continue
        if spec.code in seen_codes:
            warnings.append(f"{spec.display}: appears more than once; kept the first value.")
            continue

        # The two lines after the label must be the unit then the value.
        unit_line = _normalize(deduped[index + 1]) if index + 1 < len(deduped) else ""
        value_line = deduped[index + 2] if index + 2 < len(deduped) else ""
        if unit_line not in spec.units:
            warnings.append(f"{spec.display}: expected its unit after the label (skipped).")
            continue
        value = _metric_value(value_line)
        if value is None:
            warnings.append(f"{spec.display}: no clean numeric value found (skipped).")
            continue
        if not (spec.min_value <= value <= spec.max_value):
            warnings.append(
                f"{spec.display}: {value:g} is outside the expected range "
                f"{spec.min_value:g}–{spec.max_value:g} (skipped)."
            )
            continue
        seen_codes.add(spec.code)
        metrics.append(
            BiomechMetric(code=spec.code, display=spec.display, unit=spec.unit, value=value)
        )

    kind = _detect_kind(deduped)
    condition = _detect_condition(deduped) if kind is ReportKind.balance else None
    if kind is None:
        warnings.append("Could not determine the report kind (expected balance or gait).")
    if assessment_at is None:
        warnings.append("Could not find the date of service; no metrics can be imported.")

    return BiomechReport(
        kind=kind,
        assessment_at=assessment_at,
        device=None,
        condition=condition,
        metrics=tuple(metrics),
        warnings=tuple(warnings),
    )
