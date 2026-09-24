"""Builds the deterministic `PregameLiveComparison`.

Combines a pregame `PregameContext` (Phase 2, reused as-is) with a live
`LivePitcherMetrics` snapshot (this phase's `live_metrics.py`) into one
row per pitch type. Every number here is arithmetic on already-computed
backend values — nothing here calls an LLM, and this module has no I/O of
its own, so it is fully unit-testable against fixed inputs.
"""

from __future__ import annotations

from datetime import date

from ..pregame.sample_size import SampleStatus
from ..pregame.schemas import PitchTypeUsage, PregameContext
from .live_metrics import LivePitcherMetrics, LivePitchTypeMetric
from .sample_size import evaluate_overall, evaluate_pitch_type
from .schemas import PregameLiveComparison, PregameLiveComparisonRow
from .signals import evaluate_signals


def build_comparison(
    game_id: str,
    pitcher_id: int,
    baseline_start_date: date,
    baseline_end_date: date,
    baseline: PregameContext | None,
    live: LivePitcherMetrics,
) -> PregameLiveComparison:
    """Assemble the full comparison.

    `baseline` is `None` when the pregame source (Statcast) returned no
    pitches at all for this window — a genuinely different case from "this
    pitch type wasn't part of the baseline mix", which is instead
    represented per-row by `baseline_usage_pct == 0.0` (see `_baseline_side`
    / `_live_side` for the zero-vs-missing distinction applied to each
    side independently).
    """
    baseline_total_pitches = baseline.total_pitches if baseline else 0
    live_total_pitches = live.total_pitches

    baseline_by_type = (
        {row.pitch_type: row for row in baseline.pitch_usage_by_type} if baseline else {}
    )
    live_by_type = {row.pitch_type: row for row in live.by_type}
    pitch_types = sorted(set(baseline_by_type) | set(live_by_type))

    rows = [
        _build_row(
            pitch_type,
            baseline_by_type.get(pitch_type),
            live_by_type.get(pitch_type),
            baseline_total_pitches,
            live_total_pitches,
        )
        for pitch_type in pitch_types
    ]

    # `is_notable` depends on the comparison's full signal list (a usage
    # signal's gate looks at every pitch type's totals, not just its own
    # row), so it's finalized here, after every row already exists.
    signals = evaluate_signals(rows, baseline_total_pitches, live_total_pitches)
    notable_pitch_types = {signal.pitch_type for signal in signals}
    rows = [
        row.model_copy(update={"is_notable": row.pitch_type in notable_pitch_types})
        for row in rows
    ]

    overall_live_status = evaluate_overall(live.total_pitches)
    limitations = _limitations(baseline, live, overall_live_status)

    return PregameLiveComparison(
        game_id=game_id,
        pitcher_id=pitcher_id,
        pitcher_name=live.pitcher_name,
        baseline_start_date=baseline_start_date,
        baseline_end_date=baseline_end_date,
        baseline_available=baseline is not None and baseline.total_pitches > 0,
        baseline_total_pitches=baseline_total_pitches,
        live_available=live.total_pitches > 0,
        live_total_pitches=live_total_pitches,
        overall_live_status=overall_live_status,
        rows=rows,
        signals=signals,
        limitations=limitations,
    )


def _build_row(
    pitch_type: str,
    baseline_row: PitchTypeUsage | None,
    live_row: LivePitchTypeMetric | None,
    baseline_total_pitches: int,
    live_total_pitches: int,
) -> PregameLiveComparisonRow:
    baseline_usage_pct, baseline_velocity, baseline_sample_size, baseline_status = (
        _baseline_side(baseline_row, baseline_total_pitches)
    )
    live_usage_pct, live_velocity, live_sample_size = _live_side(live_row, live_total_pitches)

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

    live_status = evaluate_pitch_type(live_sample_size)
    status = (
        SampleStatus.SUFFICIENT
        if baseline_status is SampleStatus.SUFFICIENT and live_status is SampleStatus.SUFFICIENT
        else SampleStatus.INSUFFICIENT_SAMPLE
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
        status=status,
        # Finalized in `build_comparison` once every row's signals are known.
        is_notable=False,
    )


def _baseline_side(
    baseline_row: PitchTypeUsage | None, baseline_total_pitches: int
) -> tuple[float | None, float | None, int, SampleStatus]:
    """Usage/velocity/sample-size/status for one pitch type's baseline
    side, distinguishing "never thrown" (`None`, no baseline data at all
    for this window) from "thrown zero times this window despite the
    baseline having pitches" (`0.0`, a real, meaningful usage share).
    """
    if baseline_row is not None:
        return (
            baseline_row.percentage,
            baseline_row.avg_velocity,
            baseline_row.sample_size,
            baseline_row.status,
        )
    if baseline_total_pitches > 0:
        return 0.0, None, 0, SampleStatus.INSUFFICIENT_SAMPLE
    return None, None, 0, SampleStatus.INSUFFICIENT_SAMPLE


def _live_side(
    live_row: LivePitchTypeMetric | None, live_total_pitches: int
) -> tuple[float | None, float | None, int]:
    """Usage/velocity/sample-size for one pitch type's live side. Same
    zero-vs-missing distinction as `_baseline_side`, keyed off the
    pitcher's live total pitch count instead of the baseline total.
    """
    if live_row is not None:
        return live_row.percentage, live_row.avg_velocity, live_row.count
    if live_total_pitches > 0:
        return 0.0, None, 0
    return None, None, 0


def _limitations(
    baseline: PregameContext | None,
    live: LivePitcherMetrics,
    overall_live_status: SampleStatus,
) -> list[str]:
    limitations: list[str] = []
    if baseline is None or baseline.total_pitches == 0:
        limitations.append(
            "No pregame Statcast baseline was found for this pitcher in the given "
            "date window; live figures are shown without a comparison."
        )
    if live.total_pitches == 0:
        limitations.append(
            "This pitcher has not thrown a tracked pitch in this game's feed yet."
        )
    elif overall_live_status is SampleStatus.INSUFFICIENT_SAMPLE:
        limitations.append(
            f"Only {live.total_pitches} live pitch(es) have been tracked so far this "
            "game; usage and velocity shifts are not yet meaningful trends."
        )
    return limitations
