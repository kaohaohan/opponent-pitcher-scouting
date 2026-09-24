"""Pydantic models for the Phase 5 pregame-vs-live comparison feature.

`PregameLiveComparison` is the deterministic half — every number in it is
computed by backend code, never by Gemini. `ComparisonNote` is the only
thing a `ComparisonNoteProvider` produces: structured prose that narrates
`is_notable` rows, never numbers of its own.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..pregame.sample_size import SampleStatus


class PregameLiveComparisonRow(BaseModel):
    """One pitch type's pregame baseline vs. this game's live figures.

    `baseline_usage_pct`/`live_usage_pct` distinguish "never seen" from
    "seen, but not thrown right now": `None` means that side has no pitch
    data at all for this window (baseline/live total is `0`), while `0.0`
    means that side *does* have pitches this window, just none of this
    particular type — a genuinely different case from missing data, so it
    is never collapsed into `None`. `baseline_velocity`/`live_velocity`
    are `None` whenever that side has no measured velocity for this pitch
    type — velocity is never coerced to `0`, which would read as the
    softest pitch ever thrown. `usage_delta_pp`/`velocity_delta` are
    computed whenever both sides are non-`None` (so a `0.0` usage counts),
    and `None` only when a side is genuinely missing.
    """

    model_config = ConfigDict(extra="forbid")

    pitch_type: str
    baseline_usage_pct: float | None
    baseline_velocity: float | None
    baseline_sample_size: int
    live_usage_pct: float | None
    live_velocity: float | None
    live_sample_size: int
    usage_delta_pp: float | None
    velocity_delta: float | None
    #: Confidence in this row's delta — insufficient if either side's own
    #: sample for this pitch type is too small. See `app.comparison.sample_size`.
    status: SampleStatus
    #: True only when this pitch type has at least one `Signal` in the
    #: comparison's `signals` list (see `app.comparison.signals`) — the
    #: only rows Gemini may describe as a change.
    is_notable: bool


class Signal(BaseModel):
    """One pitch type's usage or velocity gap between baseline and today
    that cleared a product heuristic — see `app.comparison.signals` for
    the gating logic and `app.comparison.sample_size` for the thresholds.
    Not a statistical significance test: no p-value, no confidence
    interval, no claim about *why* the gap exists.
    """

    model_config = ConfigDict(extra="forbid")

    level: Literal["watch", "alert"]
    metric: Literal["usage", "velocity"]
    pitch_type: str
    pitch_name: str | None
    baseline_value: float
    today_value: float
    delta: float
    #: The pitch count this signal's sample-size gate was evaluated
    #: against: the live outing's total pitches for a `usage` signal, this
    #: pitch type's own live count for a `velocity` signal. Two signals on
    #: the same pitch type can carry different `sample_basis` values
    #: because they are gated on different denominators.
    sample_basis: int


class PregameLiveComparison(BaseModel):
    """The complete, structured comparison. The only thing a
    `ComparisonNoteProvider` sees, and what the numeric UI renders
    directly — independent of whether a note is ever generated."""

    model_config = ConfigDict(extra="forbid")

    game_id: str
    pitcher_id: int
    pitcher_name: str | None
    baseline_start_date: date
    baseline_end_date: date
    baseline_available: bool
    baseline_total_pitches: int
    live_available: bool
    live_total_pitches: int
    #: Sample status for the live outing as a whole (distinct from each
    #: row's own per-pitch-type status).
    overall_live_status: SampleStatus
    rows: list[PregameLiveComparisonRow]
    #: Every usage/velocity gap that cleared a product heuristic (see
    #: `app.comparison.signals`) — worth a user's attention, not a
    #: statistical claim. Alert-level first, then by `|delta|` descending.
    signals: list[Signal] = Field(default_factory=list)
    #: Plain-language caveats, same convention as `PregameContext.limitations`.
    limitations: list[str]


class ComparisonBaselineRequest(BaseModel):
    """The pregame baseline window to compare the live game against.
    Shared by the comparison GET (query params) and the note POST (body)."""

    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date


class NotableChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    description: str


class ComparisonNote(BaseModel):
    """Gemini's structured explanation of an already-computed
    `PregameLiveComparison`. Every field here is prose; no field here is a
    number Gemini was allowed to invent."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    notable_changes: list[NotableChange] = Field(default_factory=list)
    sample_note: str
