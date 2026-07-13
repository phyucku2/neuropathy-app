"""Unit tests for the BioMech report parser and its polarity registry (ADR-0014).

All report text is synthetic (CLAUDE.md §5). Parsing is defensive: it never raises,
never fabricates a value, and only surfaces displays from the closed registry.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.biomech.parser import METRICS, BiomechReport, ReportKind, parse_report
from app.trajectory.directionality import Polarity, polarity_for

BALANCE_REPORT = "\n".join(
    [
        "BioMech Balance Assessment Report",
        "Assessment Date: 2026-06-15T09:30:00",
        "Device: BioMech Balance Platform v3",
        "Overall Balance Score: 82 / 100",
        "Sway Velocity: 12.4 mm/s",
        "Sway Area: 340 mm2",
        "Weight Distribution: 51 / 49",  # not in V1 registry -> ignored
        "Clinician Notes: patient did great <script>alert(1)</script>",  # ignored
    ]
)

GAIT_REPORT = "\n".join(
    [
        "BioMech Gait Assessment Report",
        "Assessment Date: 2026-06-20 08:00:00",
        "Gait Speed: 1.05 m/s",
        "Cadence: 108 steps/min",
        "Step Length: 62 cm",
        "Step Time Symmetry: 96 %",
    ]
)


def _by_code(report: BiomechReport) -> dict[str, float]:
    return {metric.code: metric.value for metric in report.metrics}


def test_balance_report_parses_kind_date_device_and_metrics() -> None:
    report = parse_report(BALANCE_REPORT)
    assert report.kind is ReportKind.balance
    assert report.assessment_at == datetime(2026, 6, 15, 9, 30, 0, tzinfo=UTC)
    assert report.device == "BioMech Balance Platform v3"
    assert _by_code(report) == {
        "biomech_balance_score": 82.0,
        "biomech_sway_velocity": 12.4,
        "biomech_sway_area": 340.0,
    }
    # The first numeric token wins for "82 / 100" (the score, not the denominator).
    assert report.warnings == ()


def test_gait_report_parses_all_four_metrics() -> None:
    report = parse_report(GAIT_REPORT)
    assert report.kind is ReportKind.gait
    assert report.assessment_at == datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
    assert _by_code(report) == {
        "biomech_gait_speed": 1.05,
        "biomech_cadence": 108.0,
        "biomech_step_length": 62.0,
        "biomech_step_time_symmetry": 96.0,
    }
    assert report.warnings == ()


def test_displays_come_only_from_the_registry_never_document_text() -> None:
    report = parse_report(BALANCE_REPORT)
    displays = {metric.display for metric in report.metrics}
    assert displays == {"Balance score", "Sway velocity", "Sway area"}
    # No document free text (the <script> note, the raw labels) leaks into a display.
    assert all("<" not in metric.display for metric in report.metrics)


def test_non_numeric_value_is_skipped_with_a_warning() -> None:
    report = parse_report(
        "Balance Assessment\nAssessment Date: 2026-06-15\nBalance Score: not measured"
    )
    assert report.metrics == ()
    assert report.warnings == ("Balance score: no numeric value found (skipped).",)


def test_out_of_range_value_is_skipped_with_a_warning() -> None:
    report = parse_report(
        "Balance Assessment\nAssessment Date: 2026-06-15\n"
        "Balance Score: 250\nSway Velocity: -3 mm/s"
    )
    assert report.metrics == ()
    assert any("250" in w and "outside the expected range" in w for w in report.warnings)
    assert any("-3" in w for w in report.warnings)


def test_repeated_metric_keeps_first_value_and_warns() -> None:
    report = parse_report(
        "Balance Assessment\nAssessment Date: 2026-06-15\nBalance Score: 80\nBalance Score: 90"
    )
    assert _by_code(report) == {"biomech_balance_score": 80.0}
    assert any("appears more than once" in w for w in report.warnings)


def test_empty_text_yields_zero_metrics_and_warnings() -> None:
    report = parse_report("")
    assert report.metrics == ()
    assert report.kind is None
    assert report.assessment_at is None
    assert any("report kind" in w for w in report.warnings)
    assert any("assessment date" in w for w in report.warnings)


def test_garbage_text_yields_zero_metrics_and_warnings() -> None:
    report = parse_report("lorem ipsum\nnothing structured here\n12345 percent maybe")
    assert report.metrics == ()
    assert report.kind is None
    assert report.assessment_at is None
    assert len(report.warnings) == 2  # missing kind + missing date, nothing else


def test_missing_date_is_reported_even_when_metrics_are_present() -> None:
    report = parse_report("Balance Assessment\nBalance Score: 82")
    # A metric parsed, but without a date it cannot become an Observation.
    assert _by_code(report) == {"biomech_balance_score": 82.0}
    assert report.assessment_at is None
    assert any("assessment date" in w for w in report.warnings)


def test_unparseable_date_becomes_none_not_a_crash() -> None:
    report = parse_report("Gait Assessment\nAssessment Date: sometime last spring")
    assert report.assessment_at is None
    assert any("assessment date" in w for w in report.warnings)


def test_us_style_date_is_parsed_via_the_strptime_fallback() -> None:
    # fromisoformat rejects US m/d/Y; the explicit formats catch it and assume UTC.
    report = parse_report("Gait Assessment\nAssessment Date: 06/15/2026 09:30")
    assert report.assessment_at == datetime(2026, 6, 15, 9, 30, tzinfo=UTC)


def test_repeated_date_and_device_lines_keep_the_first() -> None:
    report = parse_report(
        "\n".join(
            [
                "Balance Assessment",
                "Assessment Date: 2026-06-15T00:00:00",
                "Assessment Date: 2027-01-01T00:00:00",  # ignored — first wins
                "Device: Platform A",
                "Device: Platform B",  # ignored — first wins
                "Balance Score: 82",
            ]
        )
    )
    assert report.assessment_at == datetime(2026, 6, 15, tzinfo=UTC)
    assert report.device == "Platform A"


def test_registry_polarities_agree_with_directionality() -> None:
    """The parser's higher_is_better and the trajectory polarity must never drift."""
    expected = {
        True: Polarity.higher_is_better,
        False: Polarity.lower_is_better,
        None: Polarity.unknown,
    }
    for spec in METRICS:
        assert polarity_for(spec.code) == expected[spec.higher_is_better], spec.code
