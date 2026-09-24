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


def test_pitch_type_missing_from_live_is_zero_not_none_when_live_has_other_pitches():
    """The pitcher threw *something* tonight (live total > 0), just not a
    Curveball — that's a real 0%, not "no data", and the delta is computed
    against it (delta = -baseline)."""
    baseline = baseline_context([baseline_row("Curveball", 25, 25.0, 78.0)])
    live = live_metrics([live_row("Slider", 10, 100.0, 86.0)])

    comparison = build_comparison("776743", 542881, START, END, baseline, live)
    curveball = next(row for row in comparison.rows if row.pitch_type == "Curveball")

    assert curveball.live_usage_pct == 0.0
    assert curveball.live_velocity is None  # no pitches thrown, so no velocity to measure
    assert curveball.live_sample_size == 0
    assert curveball.usage_delta_pp == -25.0


def test_pitch_type_missing_from_baseline_is_zero_not_none_when_baseline_has_other_pitches():
    """The baseline window has pitches (baseline total > 0), just none of
    them a Splitter — a real 0% baseline share, not missing baseline data."""
    baseline = baseline_context([baseline_row("Slider", 32, 100.0, 85.6)])
    live = live_metrics([live_row("Splitter", 8, 100.0, 84.0)])

    comparison = build_comparison("776743", 542881, START, END, baseline, live)
    by_type = {row.pitch_type: row for row in comparison.rows}
    splitter = by_type["Splitter"]
    slider = by_type["Slider"]

    assert splitter.baseline_usage_pct == 0.0
    assert splitter.baseline_velocity is None
    assert splitter.baseline_sample_size == 0
    assert splitter.usage_delta_pp == 100.0

    # The reverse also holds within the same comparison: Slider was never
    # thrown live tonight (live total > 0), so its live share is 0.0 too.
    assert slider.live_usage_pct == 0.0
    assert slider.live_velocity is None
    assert slider.usage_delta_pp == -100.0


def test_baseline_with_zero_total_pitches_is_none_not_zero():
    """Distinguish "the baseline window itself has zero pitches" (`None`,
    truly no data) from "the baseline has pitches but not this type"
    (`0.0`, tested above) — same pitch type, opposite reason for absence."""
    baseline = baseline_context([], total=0)
    live = live_metrics([live_row("Slider", 10, 100.0, 86.0)])

    comparison = build_comparison("776743", 542881, START, END, baseline, live)
    slider = next(row for row in comparison.rows if row.pitch_type == "Slider")

    assert slider.baseline_usage_pct is None
    assert slider.baseline_velocity is None
    assert slider.baseline_sample_size == 0
    assert slider.usage_delta_pp is None


def test_no_baseline_marks_baseline_unavailable_and_adds_limitation():
    live = live_metrics([live_row("Slider", 12, 100.0, 86.0)])

    comparison = build_comparison("776743", 542881, START, END, None, live)

    assert comparison.baseline_available is False
    assert comparison.baseline_total_pitches == 0
    assert any("No pregame Statcast baseline" in note for note in comparison.limitations)


def test_no_live_sample_marks_live_unavailable_and_all_live_fields_none():
    baseline = baseline_context([baseline_row("Slider", 32, 100.0, 85.6)])
    live = live_metrics([], pitcher_name=None)

    comparison = build_comparison("776743", 542881, START, END, baseline, live)
    slider = next(row for row in comparison.rows if row.pitch_type == "Slider")

    assert comparison.live_available is False
    assert comparison.overall_live_status is SampleStatus.INSUFFICIENT_SAMPLE
    assert any("not thrown a tracked pitch" in note for note in comparison.limitations)
    # Zero live pitches overall means every live field is missing data,
    # never a real 0% — there is nothing to have a share of yet.
    assert slider.live_usage_pct is None
    assert slider.live_velocity is None
    assert slider.live_sample_size == 0
    assert slider.usage_delta_pp is None


def test_row_is_insufficient_when_live_pitch_type_sample_is_below_threshold():
    # No measured velocity on either side, so this test isolates the
    # per-pitch-type sample gate on `status` from the separate signal
    # gating covered in tests/comparison/test_signals.py.
    baseline = baseline_context([baseline_row("Slider", 32, 32.0, None)])
    # 4 live sliders is below MIN_PITCH_TYPE_SAMPLE (5), even though the
    # pitcher has thrown plenty of pitches overall.
    live = live_metrics(
        [live_row("Slider", 4, 40.0, None), live_row("Four-Seam", 6, 60.0, None)]
    )

    comparison = build_comparison("776743", 542881, START, END, baseline, live)
    slider = next(row for row in comparison.rows if row.pitch_type == "Slider")

    assert slider.status is SampleStatus.INSUFFICIENT_SAMPLE
    # Baseline total (32) is well below the usage-signal floor (100), so no
    # signal fires regardless of status.
    assert slider.is_notable is False
    # The raw delta is still surfaced even though it's not "notable".
    assert slider.usage_delta_pp == 8.0


def test_is_notable_reflects_a_usage_signal_end_to_end():
    baseline = baseline_context(
        [baseline_row("Slider", 20, 20.0, 85.6), baseline_row("Four-Seam", 80, 80.0, 95.0)],
        total=100,
    )
    live = live_metrics(
        [live_row("Slider", 12, 40.0, 86.0), live_row("Four-Seam", 18, 60.0, 94.5)]
    )

    comparison = build_comparison("776743", 542881, START, END, baseline, live)
    slider = next(row for row in comparison.rows if row.pitch_type == "Slider")

    assert slider.usage_delta_pp == 20.0
    assert slider.is_notable is True
    assert any(
        signal.metric == "usage" and signal.pitch_type == "Slider" and signal.level == "alert"
        for signal in comparison.signals
    )


def test_is_notable_reflects_a_velocity_signal_end_to_end():
    baseline = baseline_context([baseline_row("Four-Seam", 44, 100.0, 95.1)])
    live = live_metrics(
        [live_row("Four-Seam", 8, 50.0, 93.5), live_row("Slider", 8, 50.0, 86.0)]
    )

    comparison = build_comparison("776743", 542881, START, END, baseline, live)
    by_type = {row.pitch_type: row for row in comparison.rows}

    assert by_type["Four-Seam"].velocity_delta == -1.6
    assert by_type["Four-Seam"].is_notable is True
    # Slider has no baseline velocity at all, so it can never get a
    # velocity signal, and its (large) usage delta is below the
    # usage-signal baseline-total floor (44 < 100).
    assert by_type["Slider"].is_notable is False
    assert [s.pitch_type for s in comparison.signals] == ["Four-Seam"]
    assert comparison.signals[0].level == "alert"
    assert comparison.signals[0].metric == "velocity"


def test_live_available_is_true_only_when_the_pitcher_has_thrown_pitches():
    baseline = baseline_context([baseline_row("Slider", 32, 32.0, 85.6)])

    comparison = build_comparison(
        "776743", 542881, START, END, baseline, live_metrics([live_row("Slider", 1, 100.0, 86.0)])
    )

    assert comparison.live_available is True
    assert comparison.live_total_pitches == 1
