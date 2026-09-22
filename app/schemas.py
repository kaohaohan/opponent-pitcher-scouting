"""Pydantic models: the normalized event contract, and API read models.

`PlateAppearanceEvent` is the single shape every source must produce. It is the
seam that lets a future `LiveSource` be swapped in without the processor, the
rule engine or the database learning anything about MLB's payloads.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Result strings are normalized to this vocabulary by the sources.
HIT_RESULTS: frozenset[str] = frozenset({"Single", "Double", "Triple", "Home Run"})
EXTRA_BASE_HIT_RESULTS: frozenset[str] = frozenset({"Double", "Triple", "Home Run"})

_MISSING_SENTINELS = {"", "-", "null", "none", "n/a", "na"}


class WatchRole(StrEnum):
    BATTER = "batter"
    PITCHER = "pitcher"


class PlateAppearanceEvent(BaseModel):
    """A normalized plate-appearance event, as emitted by any source.

    Optional Statcast fields stay `None` when the feed did not measure them.
    Blank strings and the usual "missing" placeholders are normalized to `None`
    rather than to `0.0`.
    """

    model_config = ConfigDict(extra="forbid")

    # Who
    batter_id: str = Field(min_length=1)
    batter_name: str = Field(min_length=1)
    batter_team: str = Field(min_length=1)
    pitcher_id: str | None = Field(default=None, min_length=1)
    pitcher_name: str = Field(min_length=1)
    pitcher_team: str | None = Field(default=None, min_length=1)
    matched_roles: tuple[WatchRole, ...] = Field(default=(WatchRole.BATTER,), exclude=True)

    # Where in the game
    game_id: str = Field(min_length=1)
    at_bat_index: int = Field(ge=0)
    inning: int = Field(ge=1)

    # What happened
    result: str = Field(min_length=1)
    is_complete: bool = True

    # Statcast — may legitimately be absent
    pitch_type: str | None = None
    pitch_velocity: float | None = Field(default=None, gt=0)
    exit_velocity: float | None = Field(default=None, gt=0)
    launch_angle: float | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_batter_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "batter_id" not in normalized and "external_player_id" in normalized:
            normalized["batter_id"] = normalized["external_player_id"]
        if "batter_name" not in normalized and "player_name" in normalized:
            normalized["batter_name"] = normalized["player_name"]
        if "batter_team" not in normalized and "team" in normalized:
            normalized["batter_team"] = normalized["team"]
        if "pitcher_name" not in normalized and "pitcher" in normalized:
            normalized["pitcher_name"] = normalized["pitcher"]
        for key in ("external_player_id", "player_name", "team", "pitcher"):
            normalized.pop(key, None)
        return normalized

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

    @property
    def external_player_id(self) -> str:
        return self.batter_id

    @property
    def player_name(self) -> str:
        return self.batter_name

    @property
    def team(self) -> str:
        return self.batter_team

    @property
    def pitcher(self) -> str:
        return self.pitcher_name


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
    batter_player_id: int
    pitcher_player_id: int | None
    batter_id: str
    batter_name: str
    batter_team: str
    pitcher_id: str | None
    pitcher_name: str
    pitcher_team: str | None
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
    subject_role: WatchRole
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


class LiveSyncRequest(BaseModel):
    game_id: int = Field(gt=0)
    watched_player_ids: list[int] = Field(default_factory=list)
    batter_ids: list[int] = Field(default_factory=list)
    pitcher_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_ids(self) -> LiveSyncRequest:
        self.watched_player_ids = _dedupe_positive(
            self.watched_player_ids, "watched_player_ids"
        )
        self.batter_ids = _dedupe_positive(
            [*self.watched_player_ids, *self.batter_ids], "batter_ids"
        )
        self.pitcher_ids = _dedupe_positive(self.pitcher_ids, "pitcher_ids")
        if not self.batter_ids and not self.pitcher_ids:
            raise ValueError("at least one batter_ids or pitcher_ids value is required")
        return self


def _dedupe_positive(values: list[int], field_name: str) -> list[int]:
    if any(player_id <= 0 for player_id in values):
        raise ValueError(f"{field_name} must contain positive integers")
    return list(dict.fromkeys(values))


class TeamRead(BaseModel):
    id: int | None = None
    name: str


class ParticipantRead(BaseModel):
    player_id: int
    name: str
    team_id: int | None = None
    team_name: str
    team_side: str
    roles: list[WatchRole]


class GameParticipantsRead(BaseModel):
    game_id: str
    game_state: str | None = None
    game_status: str | None = None
    teams: dict[str, TeamRead]
    participants: list[ParticipantRead]


class LiveSyncReport(ReplayReport):
    game_id: str
    game_state: str | None = None
    game_status: str | None = None
