"""Pydantic models for the Phase 5 pregame-vs-live comparison feature.

`PregameLiveComparison` is the deterministic half — every number in it is
computed by backend code, never by Gemini. `ComparisonNote` is the only
thing a `ComparisonNoteProvider` produces: structured prose that narrates
`is_notable` rows, never numbers of its own.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from ..pregame.sample_size import SampleStatus


class PregameLiveComparisonRow(BaseModel):
    """One pitch type's pregame baseline vs. this game's live figures.

    `baseline_*`/`live_*` fields are `None` when that side has no data for
    this pitch type at all (never `0`, which would read as "thrown, but
    0% of the time"). `usage_delta_pp`/`velocity_delta` are `None` unless
    both sides are present — a delta against a missing side is not a real
    number.
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
    #: True only when `status` is sufficient *and* the delta clears a
    #: magnitude floor — the only rows Gemini may describe as a change.
    is_notable: bool


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
