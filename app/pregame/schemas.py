"""Pydantic models for the pre-game brief feature.

`PitchRecord` is the normalized contract every pitch-data source must
produce, mirroring how `app.schemas.PlateAppearanceEvent` anchors Phase 1.
`PregameContext` is the only thing an `LLMProvider` ever sees: every number
in it was calculated here, in backend code, before an LLM is involved.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .sample_size import SampleStatus

_MISSING_SENTINELS = {"", "-", "null", "none", "n/a", "na"}


class PitchRecord(BaseModel):
    """One tracked pitch, normalized from a public Statcast feed.

    `release_speed` is nullable and stays `None` when unmeasured — it is
    never coerced to `0`, which would read as the softest pitch ever thrown
    rather than as an absence of data.
    """

    model_config = ConfigDict(extra="forbid")

    pitcher_id: int
    game_pk: int
    game_date: date
    at_bat_number: int = Field(ge=0)
    pitch_number: int = Field(ge=0)
    pitch_type: str = Field(min_length=1)
    balls: int = Field(ge=0)
    strikes: int = Field(ge=0)
    release_speed: float | None = Field(default=None, gt=0)

    @field_validator("release_speed", mode="before")
    @classmethod
    def _blank_is_missing(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip().lower() in _MISSING_SENTINELS:
            return None
        return value


class PitchTypeUsage(BaseModel):
    """Usage of one pitch type across all tracked pitches."""

    pitch_type: str
    count: int
    percentage: float
    sample_size: int
    status: SampleStatus
    #: Average `release_speed` for this pitch type, or `None` when every
    #: instance of it was unmeasured. Never `0.0` for "no data".
    avg_velocity: float | None = None


class PitchCountUsage(BaseModel):
    """Usage of one pitch type within one ball-strike count."""

    balls: int
    strikes: int
    pitch_type: str
    count: int
    percentage: float
    sample_size: int
    status: SampleStatus


class PregameContext(BaseModel):
    """The complete, structured brief input. The only thing an LLM sees.

    `overall_status` reflects the total pitch sample for the window;
    `pitch_usage_by_type` and `pitch_usage_by_count` each carry their own
    per-bucket `status`. `limitations` spells out, in plain language, every
    bucket an LLM must not present as a meaningful tendency.
    """

    model_config = ConfigDict(extra="forbid")

    pitcher_id: int
    start_date: date
    end_date: date
    total_pitches: int
    pitch_usage_by_type: list[PitchTypeUsage]
    pitch_usage_by_count: list[PitchCountUsage]
    overall_status: SampleStatus
    limitations: list[str]


class PregameBriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pitcher_id: int
    start_date: date
    end_date: date


class PregameBriefResponse(BaseModel):
    context: PregameContext
    brief: str


class PitcherSearchResult(BaseModel):
    """One MLB pitcher matched by name search, for the Pregame picker."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    team: str | None = None
    throws: str | None = None
