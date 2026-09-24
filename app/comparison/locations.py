"""Today-only pitch locations from a cached MLB live feed snapshot."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict

from .live_metrics import _normalize_pitch_type


class PitchLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pitch_type: str
    plate_x: float
    plate_z: float
    sz_top: float
    sz_bot: float


class PitchLocations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_pitches: int
    points: list[PitchLocation]


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def compute_pitch_locations(payload: dict[str, Any], pitcher_id: int) -> PitchLocations:
    """Include every typed arsenal pitch, even in an unfinished plate appearance."""
    total = 0
    points: list[PitchLocation] = []
    plays = payload.get("liveData", {}).get("plays", {}).get("allPlays", [])
    for play in plays:
        if not isinstance(play, dict):
            continue
        matchup = play.get("matchup")
        pitcher = matchup.get("pitcher") if isinstance(matchup, dict) else None
        if not isinstance(pitcher, dict) or pitcher.get("id") != pitcher_id:
            continue
        for event in play.get("playEvents", []) or []:
            if not isinstance(event, dict) or event.get("isPitch") is not True:
                continue
            details = event.get("details")
            pitch_type_data = details.get("type") if isinstance(details, dict) else None
            pitch_type = _normalize_pitch_type(
                pitch_type_data if isinstance(pitch_type_data, dict) else {}
            )
            if pitch_type is None:
                continue
            total += 1
            pitch_data = event.get("pitchData")
            if not isinstance(pitch_data, dict):
                continue
            coordinates = pitch_data.get("coordinates")
            if not isinstance(coordinates, dict):
                continue
            plate_x = _finite_number(coordinates.get("pX"))
            plate_z = _finite_number(coordinates.get("pZ"))
            sz_top = _finite_number(pitch_data.get("strikeZoneTop"))
            sz_bot = _finite_number(pitch_data.get("strikeZoneBottom"))
            if None in (plate_x, plate_z, sz_top, sz_bot) or sz_top <= sz_bot:
                continue
            points.append(PitchLocation(
                pitch_type=pitch_type,
                plate_x=plate_x,
                plate_z=plate_z,
                sz_top=sz_top,
                sz_bot=sz_bot,
            ))
    return PitchLocations(total_pitches=total, points=points)
