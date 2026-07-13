"""Parse extracted BioMech report text into a typed, closed-set report (ADR-0014).

BioMech's balance and gait reports are labeled `label: value unit` lines over a text
layer. Parsing is defensive and closed-set:

- **Closed metric registry (METRICS).** Only the codes V1 understands are captured;
  every one has a curated display, unit, valid range, and polarity. Unknown lines are
  ignored — free text from the document NEVER becomes a display label or a code
  (injection posture, ADR-0011). Displays come only from this registry.
- **Never crash, never fabricate.** A non-numeric or out-of-range value is skipped
  with a per-metric warning (returned to the uploader, not audited); the value is
  never coerced or invented. Empty or unrecognizable text yields a report with zero
  metrics and warnings, not an exception.

The route turns the returned report into research-grade Observations (app/biomech/
ingest.py); this module is pure (no I/O), so it is fully unit-testable.
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
    carries no clear better/worse (mirrored in app/trajectory/directionality.py).
    `labels` are the accepted (normalized) line labels that map to this metric."""

    code: str
    display: str
    unit: str
    min_value: float
    max_value: float
    higher_is_better: bool | None
    labels: tuple[str, ...]


# The closed set of metrics V1 ingests. Balance-report metrics first, then gait.
# Ranges are generous physiological bounds — their job is to reject nonsense (a negative
# score, a parse that grabbed a page number), not to make a clinical judgment.
METRICS: tuple[MetricSpec, ...] = (
    MetricSpec(
        code="biomech_balance_score",
        display="Balance score",
        unit="{score}",
        min_value=0.0,
        max_value=100.0,
        higher_is_better=True,
        labels=("balance score", "overall balance score"),
    ),
    MetricSpec(
        code="biomech_sway_velocity",
        display="Sway velocity",
        unit="mm/s",
        min_value=0.0,
        max_value=1000.0,
        higher_is_better=False,
        labels=("sway velocity", "mean sway velocity"),
    ),
    MetricSpec(
        code="biomech_sway_area",
        display="Sway area",
        unit="mm2",
        min_value=0.0,
        max_value=100000.0,
        higher_is_better=False,
        labels=("sway area",),
    ),
    MetricSpec(
        code="biomech_gait_speed",
        display="Gait speed",
        unit="m/s",
        min_value=0.0,
        max_value=10.0,
        higher_is_better=True,
        labels=("gait speed", "walking speed"),
    ),
    MetricSpec(
        code="biomech_cadence",
        display="Cadence",
        unit="{steps}/min",
        min_value=0.0,
        max_value=400.0,
        higher_is_better=None,
        labels=("cadence",),
    ),
    MetricSpec(
        code="biomech_step_length",
        display="Step length",
        unit="cm",
        min_value=0.0,
        max_value=200.0,
        higher_is_better=None,
        labels=("step length",),
    ),
    MetricSpec(
        code="biomech_step_time_symmetry",
        display="Step time symmetry",
        unit="%",
        min_value=0.0,
        max_value=100.0,
        higher_is_better=True,
        labels=("step time symmetry", "step symmetry"),
    ),
)

_SPEC_BY_LABEL: dict[str, MetricSpec] = {label: spec for spec in METRICS for label in spec.labels}

# The label lines that carry the assessment datetime and the device/source line.
_DATE_LABELS = frozenset(
    {
        "assessment date",
        "assessment date/time",
        "assessment datetime",
        "date",
        "date/time",
        "assessed",
    }
)
_DEVICE_LABELS = frozenset({"device", "instrument", "system", "source", "device id"})

# Non-ISO datetime formats to try after datetime.fromisoformat (which already covers
# ISO 8601, including space-separated and date-only). US-style dates are common on
# clinical report exports and are not ISO, so they need explicit patterns.
_DATE_FORMATS = ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y")

# A metric value must be the FULLY-CONSUMED first token of the value side — a prefix
# match would silently truncate "1,234.5" to 1.0 and store a corrupted measurement
# while reporting success (review finding). Thousands grouping and decimal commas are
# normalized explicitly; anything else numeric-ish but ambiguous (scientific notation,
# space-grouped digits, attached units) is skipped with a warning, never coerced.
# Units/ranges ("82 / 100") keep the first token, which is the measurement.
_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")
_THOUSANDS_GROUPED = re.compile(r"[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?")
_DECIMAL_COMMA = re.compile(r"[-+]?\d+,\d+")


def _metric_value(raw_value: str) -> float | None:
    """The unambiguous numeric value of a metric line, or None (research-grade: skip,
    never guess). "82 / 100" -> 82.0; "1,234.5" -> 1234.5; "1,05" -> 1.05;
    "3.2e3", "1 234.5", "1,0,5", "82/100" -> None."""
    tokens = raw_value.split()
    if not tokens:
        return None
    token = tokens[0]
    if len(tokens) > 1 and tokens[1][:1].isdigit():
        return None  # space-grouped digits ("1 234.5") are ambiguous
    if "," in token:
        if _THOUSANDS_GROUPED.fullmatch(token):
            token = token.replace(",", "")
        elif _DECIMAL_COMMA.fullmatch(token):
            token = token.replace(",", ".")
        else:
            return None
    if _NUMBER.fullmatch(token) is None:
        return None
    return float(token)


# Explicit report-kind markers: a "Report/Assessment type: balance|gait" line, or a
# "<kind> assessment" phrase. Metric labels ("balance score", "gait speed") are never
# matched because both patterns anchor on the kind word in a header position.
_KIND_TYPE_LINE = re.compile(
    r"(?im)^\s*(?:report|assessment)(?:\s+type)?\s*[:\-]\s*(balance|gait)\b"
)
_KIND_PHRASE = re.compile(r"(?i)\b(balance|gait)\s+assessment\b")

# A device/source value is provenance only; cap its length so a runaway line cannot
# bloat the payload. It is stored in quality/payload, never used as a display label.
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
    """A parsed BioMech report. `kind`/`assessment_at` are None when the text did not
    carry a recognizable marker (a warning explains); `metrics` holds only accepted,
    in-range measurements; `warnings` lists every defensive skip for the uploader."""

    kind: ReportKind | None
    assessment_at: datetime | None
    device: str | None
    metrics: tuple[BiomechMetric, ...]
    warnings: tuple[str, ...]


def _normalize_label(label: str) -> str:
    return " ".join(label.strip().lower().split())


def _parse_datetime(raw: str) -> datetime | None:
    """Parse a labeled assessment datetime; naive values are assumed UTC (like labs),
    so every report's assessment_at is tz-aware and trend math never mixes naive/aware."""
    text = raw.strip()
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in _DATE_FORMATS:
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _detect_kind(text: str) -> ReportKind | None:
    match = _KIND_TYPE_LINE.search(text) or _KIND_PHRASE.search(text)
    return ReportKind(match.group(1).lower()) if match else None


def parse_report(text: str) -> BiomechReport:
    """Parse extracted report text into a typed BiomechReport (never raises).

    Scans labeled lines: recognized metric labels become measurements (skipped with a
    warning when non-numeric, out of range, or a repeated code); the datetime and
    device lines are captured; every other line is ignored. Missing kind or datetime
    is reported as a warning, not an error.
    """
    assessment_at: datetime | None = None
    device: str | None = None
    metrics: list[BiomechMetric] = []
    warnings: list[str] = []
    seen_codes: set[str] = set()

    for line in text.splitlines():
        if ":" not in line:
            continue
        raw_label, _, raw_value = line.partition(":")
        label = _normalize_label(raw_label)

        if label in _DATE_LABELS:
            if assessment_at is None:
                assessment_at = _parse_datetime(raw_value)
            continue
        if label in _DEVICE_LABELS:
            if device is None:
                cleaned = " ".join(raw_value.split())[:_MAX_DEVICE_LEN]
                device = cleaned or None
            continue

        spec = _SPEC_BY_LABEL.get(label)
        if spec is None:
            continue  # unknown line — ignored, never a fabricated label

        value = _metric_value(raw_value)
        if value is None:
            if _NUMBER.search(raw_value) is None:
                warnings.append(f"{spec.display}: no numeric value found (skipped).")
            else:
                warnings.append(
                    f"{spec.display}: value {' '.join(raw_value.split())!r} is not an "
                    "unambiguous number (skipped)."
                )
            continue
        if not (spec.min_value <= value <= spec.max_value):
            warnings.append(
                f"{spec.display}: {value:g} is outside the expected range "
                f"{spec.min_value:g}–{spec.max_value:g} (skipped)."
            )
            continue
        if spec.code in seen_codes:
            warnings.append(f"{spec.display}: appears more than once; kept the first value.")
            continue
        seen_codes.add(spec.code)
        metrics.append(
            BiomechMetric(code=spec.code, display=spec.display, unit=spec.unit, value=value)
        )

    kind = _detect_kind(text)
    if kind is None:
        warnings.append("Could not determine the report kind (expected balance or gait).")
    if assessment_at is None:
        warnings.append("Could not find the assessment date; no metrics can be imported.")

    return BiomechReport(
        kind=kind,
        assessment_at=assessment_at,
        device=device,
        metrics=tuple(metrics),
        warnings=tuple(warnings),
    )
