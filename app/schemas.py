"""Pydantic models: the normalized event contract, and API read models.

`PlateAppearanceEvent` is the single shape every source must produce. It is the
seam that lets a future `LiveSource` be swapped in without the processor, the
rule engine or the database learning anything about MLB's payloads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Result strings are normalized to this vocabulary by the sources.
HIT_RESULTS: frozenset[str] = frozenset({"Single", "Double", "Triple", "Home Run"})
EXTRA_BASE_HIT_RESULTS: frozenset[str] = frozenset({"Double", "Triple", "Home Run"})

_MISSING_SENTINELS = {"", "-", "null", "none", "n/a", "na"}


class PlateAppearanceEvent(BaseModel):
    """A normalized plate-appearance event, as emitted by any source.

    Optional Statcast fields stay `None` when the feed did not measure them.
    Blank strings and the usual "missing" placeholders are normalized to `None`
    rather than to `0.0`.
    """

    model_config = ConfigDict(extra="forbid")

    # Who
    external_player_id: str = Field(min_length=1)
    player_name: str = Field(min_length=1)
    team: str = Field(min_length=1)

    # Where in the game
    game_id: str = Field(min_length=1)
    at_bat_index: int = Field(ge=0)
    inning: int = Field(ge=1)

    # What happened
    result: str = Field(min_length=1)
    pitcher: str = Field(min_length=1)
    is_complete: bool = True

    # Statcast — may legitimately be absent
    pitch_type: str | None = None
    pitch_velocity: float | None = Field(default=None, gt=0)
    exit_velocity: float | None = Field(default=None, gt=0)
    launch_angle: float | None = None

    @field_validator(
        "pitch_type", "pitch_velocity", "exit_velocity", "launch_angle", mode="before"
    )
    @classmethod
    def _blank_is_missing(cls, value: Any) -> Any:
        """Treat placeholder strings as absent data, never as zero."""
        if isinstance(value, str) and value.strip().lower() in _MISSING_SENTINELS:
            return None
        return value

    @property
    def is_hit(self) -> bool:
        return self.result in HIT_RESULTS

    @property
    def is_extra_base_hit(self) -> bool:
        return self.result in EXTRA_BASE_HIT_RESULTS


class PlayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_player_id: str
    name: str
    team: str


class PlateAppearanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    game_id: str
    player_id: int
    at_bat_index: int
    inning: int
    result: str
    pitcher: str
    pitch_type: str | None
    pitch_velocity: float | None
    exit_velocity: float | None
    launch_angle: float | None
    is_complete: bool


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plate_appearance_id: int
    rule_type: str
    message: str
    created_at: datetime


class ReplayReport(BaseModel):
    """Outcome of replaying a whole source, for the dev/demo endpoint."""

    source: str
    events_read: int
    stored: int
    duplicates: int
    ignored_incomplete: int
    invalid: int
    alerts_created: int
    #: Set when the source itself failed part-way through. Events already ingested
    #: before the failure are kept and counted above.
    source_error: str | None = None
