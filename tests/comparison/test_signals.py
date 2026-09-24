"""evaluate_signals: gating usage/velocity gaps into watch/alert Signals.

Usage signals are gated on each side's TOTAL pitch count (not this pitch
type's own count) — a pitch type thrown zero times tonight out of a
healthy overall sample is still a meaningful gap. Velocity signals are
gated on this ONE pitch type's own count on each side instead, since
comparing velocity only makes sense within the same type.
"""

from __future__ import annotations

from app.comparison.sample_size import (
    MIN_BASELINE_TOTAL_FOR_USAGE_SIGNAL,
    MIN_BASELINE_VELOCITY_SAMPLE,
    USAGE_ALERT_MIN_LIVE_TOTAL,
    USAGE_WATCH_DELTA_PP,
    USAGE_WATCH_MIN_LIVE_TOTAL,
    VELOCITY_ALERT_MIN_LIVE_COUNT,
    VELOCITY_WATCH_DELTA_MPH,
    VELOCITY_WATCH_MIN_LIVE_COUNT,
)
from app.comparison.schemas import PregameLiveComparisonRow
from app.comparison.signals import evaluate_signals
from app.pregame.sample_size import SampleStatus


def make_row(
    pitch_type: str = "SL",
    baseline_usage_pct: float | None = None,
    baseline_velocity: float | None = None,
    baseline_sample_size: int = 0,
    live_usage_pct: float | None = None,
    live_velocity: float | None = None,
    live_sample_size: int = 0,
) -> PregameLiveComparisonRow:
    usage_delta_pp = (
        round(live_usage_pct - baseline_usage_pct, 1)
        if baseline_usage_pct is not None and live_usage_pct is not None
        else None
    )
    velocity_delta = (
        round(live_velocity - baseline_velocity, 1)
        if baseline_velocity is not None and live_velocity is not None
        else None
    )
    return PregameLiveComparisonRow(
        pitch_type=pitch_type,
        baseline_usage_pct=baseline_usage_pct,
        baseline_velocity=baseline_velocity,
        baseline_sample_size=baseline_sample_size,
        live_usage_pct=live_usage_pct,
        live_velocity=live_velocity,
        live_sample_size=live_sample_size,
        usage_delta_pp=usage_delta_pp,
        velocity_delta=velocity_delta,
        status=SampleStatus.SUFFICIENT,
        is_notable=False,
    )


# --- Usage signals -------------------------------------------------------


def test_usage_signal_fires_on_a_thrown_zero_pitch_type_with_healthy_totals():
    """The scenario from the spec: 12 live pitches, 0 of them a slider,
    against a 23% baseline share — a real WATCH even though the slider's
    own live count is 0."""
    row = make_row(
        pitch_type="SL",
        baseline_usage_pct=23.0,
        baseline_sample_size=30,
        live_usage_pct=0.0,
        live_sample_size=0,
    )

    signals = evaluate_signals([row], baseline_total_pitches=100, live_total_pitches=12)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.level == "watch"
    assert signal.metric == "usage"
    assert signal.pitch_type == "SL"
    assert signal.baseline_value == 23.0
    assert signal.today_value == 0.0
    assert signal.delta == -23.0
    # sample_basis for a usage signal is the live OUTING total, not this
    # pitch type's own (zero) live count.
    assert signal.sample_basis == 12


def test_usage_signal_requires_baseline_total_floor_not_per_type_count():
    row = make_row(baseline_usage_pct=50.0, live_usage_pct=0.0)

    below_floor = evaluate_signals(
        [row],
        baseline_total_pitches=MIN_BASELINE_TOTAL_FOR_USAGE_SIGNAL - 1,
        live_total_pitches=USAGE_ALERT_MIN_LIVE_TOTAL,
    )
    at_floor = evaluate_signals(
        [row],
        baseline_total_pitches=MIN_BASELINE_TOTAL_FOR_USAGE_SIGNAL,
        live_total_pitches=USAGE_ALERT_MIN_LIVE_TOTAL,
    )

    assert below_floor == []
    assert len(at_floor) == 1


def test_usage_signal_requires_live_total_floor():
    row = make_row(baseline_usage_pct=50.0, live_usage_pct=0.0)

    below_floor = evaluate_signals(
        [row],
        baseline_total_pitches=MIN_BASELINE_TOTAL_FOR_USAGE_SIGNAL,
        live_total_pitches=USAGE_WATCH_MIN_LIVE_TOTAL - 1,
    )
    at_floor = evaluate_signals(
        [row],
        baseline_total_pitches=MIN_BASELINE_TOTAL_FOR_USAGE_SIGNAL,
        live_total_pitches=USAGE_WATCH_MIN_LIVE_TOTAL,
    )

    assert below_floor == []
    assert len(at_floor) == 1
    assert at_floor[0].level == "watch"


def test_usage_signal_is_alert_only_once_both_higher_total_and_higher_delta_clear():
    big_delta_row = make_row(baseline_usage_pct=40.0, live_usage_pct=25.0)  # |delta| = 15pp

    # Delta clears the alert bar, but the live total doesn't yet.
    still_watch = evaluate_signals(
        [big_delta_row],
        baseline_total_pitches=MIN_BASELINE_TOTAL_FOR_USAGE_SIGNAL,
        live_total_pitches=USAGE_ALERT_MIN_LIVE_TOTAL - 1,
    )
    assert len(still_watch) == 1
    assert still_watch[0].level == "watch"

    now_alert = evaluate_signals(
        [big_delta_row],
        baseline_total_pitches=MIN_BASELINE_TOTAL_FOR_USAGE_SIGNAL,
        live_total_pitches=USAGE_ALERT_MIN_LIVE_TOTAL,
    )
    assert len(now_alert) == 1
    assert now_alert[0].level == "alert"

    small_delta_row = make_row(baseline_usage_pct=40.0, live_usage_pct=31.0)  # |delta| = 9pp
    # High enough total for alert, but the delta itself doesn't clear it.
    delta_too_small = evaluate_signals(
        [small_delta_row],
        baseline_total_pitches=MIN_BASELINE_TOTAL_FOR_USAGE_SIGNAL,
        live_total_pitches=USAGE_ALERT_MIN_LIVE_TOTAL,
    )
    assert len(delta_too_small) == 1
    assert delta_too_small[0].level == "watch"


def test_usage_signal_boundary_deltas():
    at_watch = make_row(baseline_usage_pct=USAGE_WATCH_DELTA_PP, live_usage_pct=0.0)
    below_watch = make_row(baseline_usage_pct=USAGE_WATCH_DELTA_PP - 0.1, live_usage_pct=0.0)

    assert evaluate_signals(
        [at_watch], baseline_total_pitches=100, live_total_pitches=USAGE_WATCH_MIN_LIVE_TOTAL
    )[0].level == "watch"
    assert (
        evaluate_signals(
            [below_watch], baseline_total_pitches=100, live_total_pitches=USAGE_WATCH_MIN_LIVE_TOTAL
        )
        == []
    )


def test_usage_signal_none_on_either_side_yields_no_signal():
    missing_live = make_row(baseline_usage_pct=50.0, live_usage_pct=None)
    missing_baseline = make_row(baseline_usage_pct=None, live_usage_pct=50.0)

    assert (
        evaluate_signals(
            [missing_live], baseline_total_pitches=200, live_total_pitches=100
        )
        == []
    )
    assert (
        evaluate_signals(
            [missing_baseline], baseline_total_pitches=200, live_total_pitches=100
        )
        == []
    )


# --- Velocity signals ------------------------------------------------------


def test_velocity_signal_gated_by_this_pitch_types_own_counts():
    row = make_row(
        baseline_velocity=95.0,
        baseline_sample_size=MIN_BASELINE_VELOCITY_SAMPLE,
        live_velocity=93.5,  # |delta| = 1.5, clears alert
        live_sample_size=VELOCITY_ALERT_MIN_LIVE_COUNT,
    )

    signals = evaluate_signals([row], baseline_total_pitches=1, live_total_pitches=1)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.metric == "velocity"
    assert signal.level == "alert"
    assert signal.baseline_value == 95.0
    assert signal.today_value == 93.5
    assert signal.delta == -1.5
    # sample_basis for a velocity signal is THIS pitch type's own live
    # count, not the outing's overall total pitches.
    assert signal.sample_basis == VELOCITY_ALERT_MIN_LIVE_COUNT


def test_velocity_signal_requires_baseline_sample_floor():
    row = make_row(
        baseline_velocity=95.0,
        baseline_sample_size=MIN_BASELINE_VELOCITY_SAMPLE - 1,
        live_velocity=90.0,
        live_sample_size=VELOCITY_ALERT_MIN_LIVE_COUNT,
    )

    assert evaluate_signals([row], baseline_total_pitches=1, live_total_pitches=1) == []


def test_velocity_signal_requires_live_count_floor():
    row = make_row(
        baseline_velocity=95.0,
        baseline_sample_size=MIN_BASELINE_VELOCITY_SAMPLE,
        live_velocity=90.0,
        live_sample_size=VELOCITY_WATCH_MIN_LIVE_COUNT - 1,
    )

    assert evaluate_signals([row], baseline_total_pitches=1, live_total_pitches=1) == []


def test_velocity_signal_is_alert_only_once_both_higher_count_and_higher_delta_clear():
    big_delta_row = make_row(
        baseline_velocity=95.0,
        baseline_sample_size=MIN_BASELINE_VELOCITY_SAMPLE,
        live_velocity=93.0,  # |delta| = 2.0, clears alert delta
        live_sample_size=VELOCITY_ALERT_MIN_LIVE_COUNT - 1,
    )
    still_watch = evaluate_signals([big_delta_row], baseline_total_pitches=1, live_total_pitches=1)
    assert len(still_watch) == 1
    assert still_watch[0].level == "watch"

    small_delta_row = make_row(
        baseline_velocity=95.0,
        baseline_sample_size=MIN_BASELINE_VELOCITY_SAMPLE,
        live_velocity=93.6,  # |delta| = 1.4, below the alert delta
        live_sample_size=VELOCITY_ALERT_MIN_LIVE_COUNT,
    )
    delta_too_small = evaluate_signals(
        [small_delta_row], baseline_total_pitches=1, live_total_pitches=1
    )
    assert len(delta_too_small) == 1
    assert delta_too_small[0].level == "watch"


def test_velocity_signal_boundary_deltas():
    at_watch = make_row(
        baseline_velocity=95.0,
        baseline_sample_size=MIN_BASELINE_VELOCITY_SAMPLE,
        live_velocity=95.0 - VELOCITY_WATCH_DELTA_MPH,
        live_sample_size=VELOCITY_WATCH_MIN_LIVE_COUNT,
    )
    below_watch = make_row(
        baseline_velocity=95.0,
        baseline_sample_size=MIN_BASELINE_VELOCITY_SAMPLE,
        live_velocity=95.0 - VELOCITY_WATCH_DELTA_MPH + 0.1,
        live_sample_size=VELOCITY_WATCH_MIN_LIVE_COUNT,
    )

    assert (
        evaluate_signals([at_watch], baseline_total_pitches=1, live_total_pitches=1)[0].level
        == "watch"
    )
    assert evaluate_signals([below_watch], baseline_total_pitches=1, live_total_pitches=1) == []


def test_velocity_signal_none_on_either_side_yields_no_signal():
    missing_live = make_row(
        baseline_velocity=95.0, baseline_sample_size=30, live_velocity=None, live_sample_size=10
    )
    missing_baseline = make_row(
        baseline_velocity=None, baseline_sample_size=30, live_velocity=90.0, live_sample_size=10
    )

    assert evaluate_signals([missing_live], baseline_total_pitches=1, live_total_pitches=1) == []
    assert (
        evaluate_signals([missing_baseline], baseline_total_pitches=1, live_total_pitches=1) == []
    )


# --- Cross-cutting: one per (metric, pitch_type), sorting -------------------


def test_at_most_one_signal_per_metric_and_pitch_type_at_the_highest_level():
    row = make_row(
        pitch_type="SL",
        baseline_usage_pct=10.0,
        live_usage_pct=30.0,  # |delta| = 20pp: clears both watch and alert
        baseline_velocity=95.0,
        baseline_sample_size=MIN_BASELINE_VELOCITY_SAMPLE,
        live_velocity=93.0,  # |delta| = 2.0: clears both watch and alert
        live_sample_size=VELOCITY_ALERT_MIN_LIVE_COUNT,
    )

    signals = evaluate_signals(
        [row],
        baseline_total_pitches=MIN_BASELINE_TOTAL_FOR_USAGE_SIGNAL,
        live_total_pitches=USAGE_ALERT_MIN_LIVE_TOTAL,
    )

    assert len(signals) == 2
    metrics = {signal.metric: signal.level for signal in signals}
    assert metrics == {"usage": "alert", "velocity": "alert"}


def test_signals_sort_alert_first_then_by_delta_descending():
    small_alert = make_row(pitch_type="SL", baseline_usage_pct=10.0, live_usage_pct=21.0)  # 11pp
    big_alert = make_row(pitch_type="CU", baseline_usage_pct=10.0, live_usage_pct=40.0)  # 30pp
    watch_only = make_row(pitch_type="FF", baseline_usage_pct=10.0, live_usage_pct=19.0)  # 9pp

    signals = evaluate_signals(
        [small_alert, big_alert, watch_only],
        baseline_total_pitches=MIN_BASELINE_TOTAL_FOR_USAGE_SIGNAL,
        live_total_pitches=USAGE_ALERT_MIN_LIVE_TOTAL,
    )

    assert [(s.pitch_type, s.level) for s in signals] == [
        ("CU", "alert"),
        ("SL", "alert"),
        ("FF", "watch"),
    ]
