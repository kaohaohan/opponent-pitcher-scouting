"""Signal detection over an already-built `PregameLiveComparison`.

Turns the per-pitch-type rows `app.comparison.compare` already computed
into a flat list of `Signal`s: usage or velocity gaps between baseline and
today that clear one of the thresholds in `app.comparison.sample_size`.
Pure function of already-computed numbers — no I/O, no LLM.

IMPORTANT: these are **product heuristics** for "worth a user's glance",
not statistical significance tests. A `watch` or `alert` here carries no
p-value, no confidence interval, and no claim about *why* a number moved —
only that it moved by enough, backed by enough pitches, to flag. See
`app.comparison.sample_size` for the exact thresholds.
"""

from __future__ import annotations

from .sample_size import (
    MIN_BASELINE_TOTAL_FOR_USAGE_SIGNAL,
    MIN_BASELINE_VELOCITY_SAMPLE,
    USAGE_ALERT_DELTA_PP,
    USAGE_ALERT_MIN_LIVE_TOTAL,
    USAGE_WATCH_DELTA_PP,
    USAGE_WATCH_MIN_LIVE_TOTAL,
    VELOCITY_ALERT_DELTA_MPH,
    VELOCITY_ALERT_MIN_LIVE_COUNT,
    VELOCITY_WATCH_DELTA_MPH,
    VELOCITY_WATCH_MIN_LIVE_COUNT,
)
from .schemas import PregameLiveComparisonRow, Signal

#: Short Statcast-style pitch type code -> human-readable name, for
#: `Signal.pitch_name`. Not exhaustive — an unrecognized code just leaves
#: `pitch_name` as `None`, same convention as the frontend's own
#: `pitchName()` lookup (`frontend/lib/adapters.ts`).
_PITCH_TYPE_NAMES: dict[str, str] = {
    "CH": "Changeup",
    "CU": "Curveball",
    "FA": "Fastball",
    "FC": "Cutter",
    "FF": "Four-seam",
    "FS": "Splitter",
    "FT": "Two-seam fastball",
    "KC": "Knuckle curve",
    "KN": "Knuckleball",
    "SC": "Screwball",
    "SI": "Sinker",
    "SL": "Slider",
    "ST": "Sweeper",
    "SV": "Slurve",
}


def _pitch_name(pitch_type: str) -> str | None:
    return _PITCH_TYPE_NAMES.get(pitch_type.upper())


def evaluate_signals(
    rows: list[PregameLiveComparisonRow],
    baseline_total_pitches: int,
    live_total_pitches: int,
) -> list[Signal]:
    """One signal per (metric, pitch_type) at most — the highest level
    that row's delta clears. Sorted alert-level first, then by `|delta|`
    descending, so the most attention-worthy signal leads.
    """
    signals: list[Signal] = []
    for row in rows:
        usage_signal = _usage_signal(row, baseline_total_pitches, live_total_pitches)
        if usage_signal is not None:
            signals.append(usage_signal)
        velocity_signal = _velocity_signal(row)
        if velocity_signal is not None:
            signals.append(velocity_signal)
    signals.sort(key=lambda signal: (signal.level != "alert", -abs(signal.delta)))
    return signals


def _usage_signal(
    row: PregameLiveComparisonRow,
    baseline_total_pitches: int,
    live_total_pitches: int,
) -> Signal | None:
    """A usage signal is gated on each side's TOTAL pitch count, not this
    pitch type's own count — a type thrown 0 of 12 live pitches is still
    a meaningful "hasn't gone to it yet" gap, so a `0.0` usage on either
    side is a valid input here, never treated as missing.
    """
    if row.baseline_usage_pct is None or row.live_usage_pct is None:
        return None
    if row.usage_delta_pp is None:
        return None
    if baseline_total_pitches < MIN_BASELINE_TOTAL_FOR_USAGE_SIGNAL:
        return None
    if live_total_pitches < USAGE_WATCH_MIN_LIVE_TOTAL:
        return None

    delta = abs(row.usage_delta_pp)
    if live_total_pitches >= USAGE_ALERT_MIN_LIVE_TOTAL and delta >= USAGE_ALERT_DELTA_PP:
        level = "alert"
    elif delta >= USAGE_WATCH_DELTA_PP:
        level = "watch"
    else:
        return None

    return Signal(
        level=level,
        metric="usage",
        pitch_type=row.pitch_type,
        pitch_name=_pitch_name(row.pitch_type),
        baseline_value=row.baseline_usage_pct,
        today_value=row.live_usage_pct,
        delta=row.usage_delta_pp,
        sample_basis=live_total_pitches,
    )


def _velocity_signal(row: PregameLiveComparisonRow) -> Signal | None:
    """A velocity signal is gated on this ONE pitch type's own count on
    each side — comparing velocity only makes sense within the same type.
    """
    if row.baseline_velocity is None or row.live_velocity is None:
        return None
    if row.velocity_delta is None:
        return None
    if row.baseline_sample_size < MIN_BASELINE_VELOCITY_SAMPLE:
        return None
    if row.live_sample_size < VELOCITY_WATCH_MIN_LIVE_COUNT:
        return None

    delta = abs(row.velocity_delta)
    if row.live_sample_size >= VELOCITY_ALERT_MIN_LIVE_COUNT and delta >= VELOCITY_ALERT_DELTA_MPH:
        level = "alert"
    elif delta >= VELOCITY_WATCH_DELTA_MPH:
        level = "watch"
    else:
        return None

    return Signal(
        level=level,
        metric="velocity",
        pitch_type=row.pitch_type,
        pitch_name=_pitch_name(row.pitch_type),
        baseline_value=row.baseline_velocity,
        today_value=row.live_velocity,
        delta=row.velocity_delta,
        sample_basis=row.live_sample_size,
    )
