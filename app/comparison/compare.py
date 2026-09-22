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
from .sample_size import (
    NOTABLE_USAGE_DELTA_PP,
    NOTABLE_VELOCITY_DELTA_MPH,
    evaluate_overall,
    evaluate_pitch_type,
)
from .schemas import PregameLiveComparison, PregameLiveComparisonRow


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
    represented per-row by `baseline_sample_size == 0`.
    """
    baseline_by_type = (
        {row.pitch_type: row for row in baseline.pitch_usage_by_type} if baseline else {}
    )
    live_by_type = {row.pitch_type: row for row in live.by_type}
    pitch_types = sorted(set(baseline_by_type) | set(live_by_type))

    rows = [
        _build_row(pitch_type, baseline_by_type.get(pitch_type), live_by_type.get(pitch_type))
        for pitch_type in pitch_types
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
        baseline_total_pitches=baseline.total_pitches if baseline else 0,
        live_available=live.total_pitches > 0,
        live_total_pitches=live.total_pitches,
        overall_live_status=overall_live_status,
        rows=rows,
        limitations=limitations,
    )


def _build_row(
    pitch_type: str,
    baseline_row: PitchTypeUsage | None,
    live_row: LivePitchTypeMetric | None,
) -> PregameLiveComparisonRow:
    baseline_usage_pct = baseline_row.percentage if baseline_row else None
    baseline_velocity = baseline_row.avg_velocity if baseline_row else None
    baseline_sample_size = baseline_row.sample_size if baseline_row else 0
    baseline_status = baseline_row.status if baseline_row else SampleStatus.INSUFFICIENT_SAMPLE

    live_usage_pct = live_row.percentage if live_row else None
    live_velocity = live_row.avg_velocity if live_row else None
    live_sample_size = live_row.count if live_row else 0

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

    is_notable = status is SampleStatus.SUFFICIENT and (
        (usage_delta_pp is not None and abs(usage_delta_pp) >= NOTABLE_USAGE_DELTA_PP)
        or (velocity_delta is not None and abs(velocity_delta) >= NOTABLE_VELOCITY_DELTA_MPH)
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
        is_notable=is_notable,
    )


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
