"""Unit tests for the BioMech report parser and its polarity registry (ADR-0014;
real report format per ADR-0036).

All report text is synthetic (CLAUDE.md §5) and mirrors the REAL pypdf line structure:
each field on its own line (label → unit → value → [range]), with bold rows duplicated.
Parsing is defensive: it never raises, never fabricates a value, and only surfaces
displays from the closed registry.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.biomech.parser import METRICS, BiomechReport, ReportKind, parse_report
from app.trajectory.directionality import Polarity, polarity_for


def _balance_report(
    *,
    eyes_open: bool = True,
    balance_score: str = "93",
    speed_normal: str = "97",
    movement_normal: str = "97",
    position_normal: str = "80",
    date: str = "3/6/25",
) -> str:
    stance = (
        ["PARALLEL APART,", "EYES OPEN,"] if eyes_open else ["PARALLEL TOGETHER,", "EYES CLOSED,"]
    )
    return "\n".join(
        [
            "13550 Waterford Place, Midlothian, VA 23112",
            "BALANCE INDIVIDUAL TEST REPORT",
            *stance,
            "30 SEC,",
            "(Static, Stable Surface)",
            "Date of Service:",
            date,
            "COMPOSITE SCORE",
            "Balance Score",
            "Percent",
            balance_score,
            "0 - 100",
            "Average Speed",  # raw sub-metric — not registered, ignored
            "Deg/sec",
            "1.9",
            "Average Speed % Normal",
            "Percent",
            speed_normal,
            "0 - 100",
            "Average Movement % Normal",
            "Percent",
            movement_normal,
            "0 - 100",
            "Average Position % Normal",
            "Percent",
            position_normal,
            "0 - 100",
        ]
    )


def _gait_report(
    *,
    gait_score: str = "85",
    total_steps: str = "70",
    cadence: str = "97",
    impact_symmetry: str = "96",
    support_ratio: str = "100",
    single_support_symmetry: str = "96",
    pelvic_neutral: str = "62",
    step_length: str | None = None,
    date: str = "3/6/25",
) -> str:
    lines = [
        "GAIT INDIVIDUAL TEST REPORT",
        "(No Aid)",
        "Date of Service:",
        date,
        "COMPOSITE SCORE",
        "Gait Score",
        "Percent",
        gait_score,
        "0 - 100",
        "Total Steps",
        "Steps",
        total_steps,
    ]
    if step_length is not None:
        lines += ["Average Step Length", "Feet", step_length]
    lines += [
        "Cadence",
        "Steps / min",
        cadence,
        "100 Steps / min",
        "Impact Symmetry (Left / Right) % Normal",
        "Percent",
        impact_symmetry,
        "0 - 100",
        "Support Ratio % Normal (Single:Double)",
        "Percent",
        support_ratio,
        "0 - 100",
        "Single Support Symmetry (Left / Right) % Normal",
        "Percent",
        single_support_symmetry,
        "0 - 100",
        "Pelvic Tilt % Neutral",
        "Percent",
        pelvic_neutral,
        "0 - 100",
    ]
    return "\n".join(lines)


def _by_code(report: BiomechReport) -> dict[str, float]:
    return {metric.code: metric.value for metric in report.metrics}


# --- happy paths -----------------------------------------------------------------------


def test_balance_report_parses_kind_date_condition_and_metrics() -> None:
    report = parse_report(_balance_report())
    assert report.kind is ReportKind.balance
    assert report.assessment_at == datetime(2025, 3, 6, tzinfo=UTC)
    assert report.condition == "PARALLEL APART, EYES OPEN"
    assert _by_code(report) == {
        "biomech_balance_score": 93.0,
        "biomech_balance_speed_normal": 97.0,
        "biomech_balance_movement_normal": 97.0,
        "biomech_balance_position_normal": 80.0,
    }
    assert report.warnings == ()


def test_gait_report_parses_all_metrics() -> None:
    report = parse_report(_gait_report(step_length="2.3"))
    assert report.kind is ReportKind.gait
    assert report.assessment_at == datetime(2025, 3, 6, tzinfo=UTC)
    assert report.condition is None  # condition is a balance concept only
    assert _by_code(report) == {
        "biomech_gait_score": 85.0,
        "biomech_total_steps": 70.0,
        "biomech_step_length": 2.3,
        "biomech_cadence": 97.0,
        "biomech_impact_symmetry": 96.0,
        "biomech_support_ratio": 100.0,
        "biomech_single_support_symmetry": 96.0,
        "biomech_pelvic_tilt_neutral": 62.0,
    }
    assert report.warnings == ()


def test_eyes_closed_condition_is_captured() -> None:
    report = parse_report(_balance_report(eyes_open=False, balance_score="92"))
    assert report.condition == "PARALLEL TOGETHER, EYES CLOSED"
    assert _by_code(report)["biomech_balance_score"] == 92.0


def test_bold_row_duplication_is_collapsed() -> None:
    # pypdf duplicates bold lines; the parser must still read one clean metric.
    text = "\n".join(
        [
            "BALANCE INDIVIDUAL TEST REPORT",
            "BALANCE INDIVIDUAL TEST REPORT",
            "Date of Service:",
            "Date of Service:",
            "3/6/25",
            "Balance Score",
            "Balance Score",
            "Percent",
            "93",
            "93",
            "0 - 100",
        ]
    )
    report = parse_report(text)
    assert _by_code(report) == {"biomech_balance_score": 93.0}
    assert report.assessment_at == datetime(2025, 3, 6, tzinfo=UTC)


def test_displays_come_only_from_the_registry() -> None:
    report = parse_report(_balance_report())
    displays = {metric.display for metric in report.metrics}
    assert displays == {
        "Balance score",
        "Balance speed (normalized)",
        "Balance movement (normalized)",
        "Balance position (normalized)",
    }


# --- defensive skips -------------------------------------------------------------------


def test_na_step_length_is_skipped_with_a_warning() -> None:
    report = parse_report(_gait_report(step_length="N/A"))
    assert "biomech_step_length" not in _by_code(report)
    assert any("Step length" in w and "no clean numeric value" in w for w in report.warnings)


def test_split_value_is_not_read_as_a_metric() -> None:
    # A registered label whose value is a left/right split ("96 / 90") is skipped.
    text = "\n".join(
        [
            "BALANCE INDIVIDUAL TEST REPORT",
            "Date of Service:",
            "3/6/25",
            "Balance Score",
            "Percent",
            "96 / 90",
        ]
    )
    report = parse_report(text)
    assert _by_code(report) == {}
    assert any("no clean numeric value" in w for w in report.warnings)


def test_out_of_range_value_is_skipped_with_a_warning() -> None:
    report = parse_report(_balance_report(balance_score="250"))
    assert "biomech_balance_score" not in _by_code(report)
    assert any("250" in w and "outside the expected range" in w for w in report.warnings)


def test_wrong_unit_after_label_is_skipped() -> None:
    # A label that is NOT followed by its expected unit is a mis-alignment — skipped.
    text = "\n".join(
        [
            "BALANCE INDIVIDUAL TEST REPORT",
            "Date of Service:",
            "3/6/25",
            "Balance Score",
            "Degrees",
            "93",
        ]
    )
    report = parse_report(text)
    assert _by_code(report) == {}
    assert any("expected its unit" in w for w in report.warnings)


def test_repeated_metric_keeps_first_value_and_warns() -> None:
    text = "\n".join(
        [
            "BALANCE INDIVIDUAL TEST REPORT",
            "Date of Service:",
            "3/6/25",
            "Balance Score",
            "Percent",
            "80",
            "0 - 100",
            "Balance Score",
            "Percent",
            "90",
        ]
    )
    report = parse_report(text)
    assert _by_code(report) == {"biomech_balance_score": 80.0}
    assert any("appears more than once" in w for w in report.warnings)


def test_empty_text_yields_zero_metrics_and_warnings() -> None:
    report = parse_report("")
    assert report.metrics == ()
    assert report.kind is None
    assert report.assessment_at is None
    assert any("report kind" in w for w in report.warnings)
    assert any("date of service" in w for w in report.warnings)


def test_garbage_text_yields_zero_metrics_and_two_warnings() -> None:
    report = parse_report("lorem ipsum\nnothing structured here\n12345 percent maybe")
    assert report.metrics == ()
    assert report.kind is None
    assert report.assessment_at is None
    assert len(report.warnings) == 2  # missing kind + missing date, nothing else


def test_missing_date_is_reported_even_when_metrics_are_present() -> None:
    text = "\n".join(["BALANCE INDIVIDUAL TEST REPORT", "Balance Score", "Percent", "93"])
    report = parse_report(text)
    assert _by_code(report) == {"biomech_balance_score": 93.0}
    assert report.assessment_at is None
    assert any("date of service" in w for w in report.warnings)


def test_unparseable_date_becomes_none_not_a_crash() -> None:
    text = "\n".join(["GAIT INDIVIDUAL TEST REPORT", "Date of Service:", "sometime last spring"])
    report = parse_report(text)
    assert report.assessment_at is None
    assert any("date of service" in w for w in report.warnings)


def test_registry_polarities_agree_with_directionality() -> None:
    """The parser's higher_is_better and the trajectory polarity must never drift."""
    expected = {
        True: Polarity.higher_is_better,
        False: Polarity.lower_is_better,
        None: Polarity.unknown,
    }
    for spec in METRICS:
        assert polarity_for(spec.code) == expected[spec.higher_is_better], spec.code
