"""build_comparison: pure combination of a pregame baseline and live
pitch metrics into PregameLiveComparison rows."""

from __future__ import annotations

from datetime import date

from app.comparison.compare import build_comparison
from app.comparison.live_metrics import LivePitcherMetrics, LivePitchTypeMetric
from app.pregame.sample_size import SampleStatus
from app.pregame.schemas import PitchTypeUsage, PregameContext

START = date(2025, 8, 1)
END = date(2025, 8, 15)


def baseline_row(
    pitch_type: str, count: int, percentage: float, avg_velocity: float | None
) -> PitchTypeUsage:
    return PitchTypeUsage(
        pitch_type=pitch_type,
        count=count,
        percentage=percentage,
        sample_size=count,
        status=SampleStatus.SUFFICIENT if count >= 20 else SampleStatus.INSUFFICIENT_SAMPLE,
        avg_velocity=avg_velocity,
    )


def baseline_context(rows: list[PitchTypeUsage], total: int | None = None) -> PregameContext:
    return PregameContext(
        pitcher_id=542881,
        start_date=START,
        end_date=END,
        total_pitches=total if total is not None else sum(row.count for row in rows),
        pitch_usage_by_type=rows,
        pitch_usage_by_count=[],
        overall_status=SampleStatus.SUFFICIENT,
        limitations=[],
    )


def live_row(
    pitch_type: str, count: int, percentage: float, avg_velocity: float | None
) -> LivePitchTypeMetric:
    return LivePitchTypeMetric(
        pitch_type=pitch_type, count=count, percentage=percentage, avg_velocity=avg_velocity
    )


def live_metrics(
    rows: list[LivePitchTypeMetric], pitcher_name: str | None = "Tyler Anderson"
) -> LivePitcherMetrics:
    return LivePitcherMetrics(
        pitcher_id=542881,
        pitcher_name=pitcher_name,
        total_pitches=sum(row.count for row in rows),
        by_type=rows,
    )


def test_computes_usage_and_velocity_deltas_for_a_shared_pitch_type():
    baseline = baseline_context([baseline_row("Slider", 32, 32.0, 85.6)])
    live = live_metrics(
        [live_row("Slider", 6, 47.0, 86.2), live_row("Four-Seam", 4, 31.0, 93.8)]
    )

    comparison = build_comparison("776743", 542881, START, END, baseline, live)
    slider = next(row for row in comparison.rows if row.pitch_type == "Slider")

    assert slider.baseline_usage_pct == 32.0
    assert slider.live_usage_pct == 47.0
    assert slider.usage_delta_pp == 15.0
    assert slider.baseline_velocity == 85.6
    assert slider.live_velocity == 86.2
    assert slider.velocity_delta == 0.6


def test_pitch_type_only_in_baseline_has_none_live_fields_and_no_delta():
    baseline = baseline_context([baseline_row("Curveball", 25, 25.0, 78.0)])
    live = live_metrics([live_row("Slider", 10, 100.0, 86.0)])

    comparison = build_comparison("776743", 542881, START, END, baseline, live)
    curveball = next(row for row in comparison.rows if row.pitch_type == "Curveball")

    assert curveball.live_usage_pct is None
    assert curveball.live_velocity is None
    assert curveball.live_sample_size == 0
    assert curveball.usage_delta_pp is None
    assert curveball.velocity_delta is None


def test_pitch_type_only_live_has_none_baseline_fields_and_no_delta():
    baseline = baseline_context([baseline_row("Slider", 32, 100.0, 85.6)])
    live = live_metrics([live_row("Splitter", 8, 100.0, 84.0)])

    comparison = build_comparison("776743", 542881, START, END, baseline, live)
    splitter = next(row for row in comparison.rows if row.pitch_type == "Splitter")

    assert splitter.baseline_usage_pct is None
    assert splitter.baseline_velocity is None
    assert splitter.baseline_sample_size == 0


def test_no_baseline_marks_baseline_unavailable_and_adds_limitation():
    live = live_metrics([live_row("Slider", 12, 100.0, 86.0)])

    comparison = build_comparison("776743", 542881, START, END, None, live)

    assert comparison.baseline_available is False
    assert comparison.baseline_total_pitches == 0
    assert any("No pregame Statcast baseline" in note for note in comparison.limitations)


def test_no_live_sample_marks_live_unavailable_and_adds_limitation():
    baseline = baseline_context([baseline_row("Slider", 32, 100.0, 85.6)])
    live = live_metrics([], pitcher_name=None)

    comparison = build_comparison("776743", 542881, START, END, baseline, live)

    assert comparison.live_available is False
    assert comparison.overall_live_status is SampleStatus.INSUFFICIENT_SAMPLE
    assert any("not thrown a tracked pitch" in note for note in comparison.limitations)


def test_row_is_insufficient_when_live_pitch_type_sample_is_below_threshold():
    baseline = baseline_context([baseline_row("Slider", 32, 32.0, 85.6)])
    # 4 live sliders is below MIN_PITCH_TYPE_SAMPLE (5), even though the
    # pitcher has thrown plenty of pitches overall.
    live = live_metrics(
        [live_row("Slider", 4, 40.0, 90.0), live_row("Four-Seam", 6, 60.0, 95.0)]
    )

    comparison = build_comparison("776743", 542881, START, END, baseline, live)
    slider = next(row for row in comparison.rows if row.pitch_type == "Slider")

    assert slider.status is SampleStatus.INSUFFICIENT_SAMPLE
    assert slider.is_notable is False
    # The raw delta is still surfaced even though it's not "notable".
    assert slider.usage_delta_pp == 8.0


def test_row_is_notable_only_when_sufficient_and_delta_clears_the_usage_floor():
    baseline = baseline_context([baseline_row("Slider", 32, 32.0, 85.6)])
    live = live_metrics(
        [live_row("Slider", 6, 47.0, 86.0), live_row("Four-Seam", 5, 53.0, 94.0)]
    )

    comparison = build_comparison("776743", 542881, START, END, baseline, live)
    slider = next(row for row in comparison.rows if row.pitch_type == "Slider")

    assert slider.status is SampleStatus.SUFFICIENT
    assert slider.usage_delta_pp == 15.0  # clears NOTABLE_USAGE_DELTA_PP (10.0)
    assert slider.is_notable is True


def test_row_is_not_notable_when_delta_is_below_both_floors():
    baseline = baseline_context([baseline_row("Slider", 32, 32.0, 85.6)])
    live = live_metrics(
        [live_row("Slider", 6, 35.0, 86.0), live_row("Four-Seam", 11, 65.0, 94.0)]
    )

    comparison = build_comparison("776743", 542881, START, END, baseline, live)
    slider = next(row for row in comparison.rows if row.pitch_type == "Slider")

    assert slider.status is SampleStatus.SUFFICIENT
    assert abs(slider.usage_delta_pp) < 10.0
    assert slider.is_notable is False


def test_row_is_notable_on_velocity_delta_alone():
    baseline = baseline_context([baseline_row("Four-Seam", 44, 44.0, 95.1)])
    live = live_metrics(
        [live_row("Four-Seam", 6, 44.0, 93.5), live_row("Slider", 8, 56.0, 86.0)]
    )

    comparison = build_comparison("776743", 542881, START, END, baseline, live)
    fastball = next(row for row in comparison.rows if row.pitch_type == "Four-Seam")

    assert fastball.usage_delta_pp == 0.0
    assert fastball.velocity_delta == -1.6
    assert fastball.is_notable is True


def test_live_available_is_true_only_when_the_pitcher_has_thrown_pitches():
    baseline = baseline_context([baseline_row("Slider", 32, 32.0, 85.6)])

    comparison = build_comparison(
        "776743", 542881, START, END, baseline, live_metrics([live_row("Slider", 1, 100.0, 86.0)])
    )

    assert comparison.live_available is True
    assert comparison.live_total_pitches == 1
