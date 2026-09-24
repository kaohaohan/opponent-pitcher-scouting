"""Live pitch-mix aggregation from one MLB feed snapshot.

Pure functions from a raw feed payload to pitch-type metrics: no I/O, no
LLM, no database. `LiveSource` already fetches this exact payload for
Phase 3/4 event ingestion (see `LiveSource.fetch_snapshot`); this module
reads pitch-level detail out of it that the Phase 1-4 pipeline discards
(it only keeps each plate appearance's terminal pitch).

Every pitch event in `liveData.plays.allPlays[*].playEvents`, not just the
one belonging to a completed plate appearance, is counted here — a batter
mid at-bat has still seen real pitches, and Phase 5 wants a comparison
against the pitcher's outing so far, not just its finished at-bats.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..pregame.sources.statcast import NON_ARSENAL_PITCH_TYPES

#: The MLB live feed's `details.type` usually carries a short `code`
#: (e.g. `"FF"`) alongside its human-readable `description` (e.g.
#: `"Four-Seam Fastball"`) — the same vocabulary Baseball Savant's
#: `pitch_type` CSV column uses (`app.pregame.sources.statcast`). `code`
#: is used directly when present. A feed snapshot that carries only
#: `description` (as this project's trimmed test fixtures do) is mapped
#: through this table instead, so a live pitch type still lines up with
#: its pregame baseline counterpart rather than silently never matching
#: because `"Four-Seam Fastball"` != `"FF"`.
_DESCRIPTION_TO_CODE: dict[str, str] = {
    "changeup": "CH",
    "curveball": "CU",
    "cutter": "FC",
    "eephus": "EP",
    "fastball": "FA",
    "four-seam fastball": "FF",
    "forkball": "FO",
    "intentional ball": "IN",
    "automatic ball": "AB",
    "pitchout": "PO",
    "knuckle curve": "KC",
    "knuckleball": "KN",
    "screwball": "SC",
    "sinker": "SI",
    "slider": "SL",
    "slurve": "SV",
    "splitter": "FS",
    "split-finger": "FS",
    "sweeper": "ST",
    "two-seam fastball": "FT",
}


class LivePitchTypeMetric(BaseModel):
    """One pitch type's live count, share, and average velocity."""

    model_config = ConfigDict(extra="forbid")

    pitch_type: str
    count: int
    percentage: float
    avg_velocity: float | None


class LivePitcherMetrics(BaseModel):
    """Every pitch a pitcher has thrown in this game so far, by type."""

    model_config = ConfigDict(extra="forbid")

    pitcher_id: int
    #: `None` when the pitcher has not appeared in any play in this feed
    #: snapshot yet.
    pitcher_name: str | None
    total_pitches: int
    by_type: list[LivePitchTypeMetric]


def compute_live_pitcher_metrics(payload: dict[str, Any], pitcher_id: int) -> LivePitcherMetrics:
    """Aggregate one pitcher's pitch-type usage and velocity from a raw
    MLB feed snapshot.

    Pitch events without an identifiable pitch type are excluded from
    both the count and the percentage denominator, mirroring how
    `app.pregame.sources.statcast.parse_csv_rows` treats untyped rows —
    both sides of the comparison drop what they can't type.
    """
    pitcher_name: str | None = None
    counts: dict[str, int] = defaultdict(int)
    speeds: dict[str, list[float]] = defaultdict(list)

    plays = payload.get("liveData", {}).get("plays", {}).get("allPlays", [])
    for play in plays:
        if not isinstance(play, dict):
            continue
        matchup = play.get("matchup") if isinstance(play.get("matchup"), dict) else {}
        pitcher = matchup.get("pitcher") if isinstance(matchup.get("pitcher"), dict) else {}
        if pitcher.get("id") != pitcher_id:
            continue
        if pitcher_name is None and isinstance(pitcher.get("fullName"), str):
            pitcher_name = pitcher["fullName"]

        for event in play.get("playEvents", []) or []:
            if not isinstance(event, dict) or event.get("isPitch") is not True:
                continue
            details = event.get("details") if isinstance(event.get("details"), dict) else {}
            pitch_type_data = details.get("type") if isinstance(details.get("type"), dict) else {}
            pitch_type = _normalize_pitch_type(pitch_type_data)
            if pitch_type is None:
                continue

            counts[pitch_type] += 1
            pitch_data = event.get("pitchData") if isinstance(event.get("pitchData"), dict) else {}
            start_speed = pitch_data.get("startSpeed")
            if isinstance(start_speed, int | float):
                speeds[pitch_type].append(float(start_speed))

    total = sum(counts.values())
    by_type = [
        LivePitchTypeMetric(
            pitch_type=pitch_type,
            count=count,
            percentage=round(count / total * 100, 1) if total else 0.0,
            avg_velocity=_average(speeds.get(pitch_type)),
        )
        for pitch_type, count in counts.items()
    ]
    by_type.sort(key=lambda row: (-row.count, row.pitch_type))

    return LivePitcherMetrics(
        pitcher_id=pitcher_id,
        pitcher_name=pitcher_name,
        total_pitches=total,
        by_type=by_type,
    )


def _average(values: list[float] | None) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _normalize_pitch_type(pitch_type_data: dict[str, Any]) -> str | None:
    """Return a Statcast-style short code for one pitch event's type.

    Prefers the feed's own `code`; falls back to mapping `description`
    through `_DESCRIPTION_TO_CODE`; falls back to the raw description
    itself (still usable as a live-only row, just not one that can line
    up with a pregame baseline row) when neither is recognized. A
    non-arsenal throw (pitchout, intentional ball, ...) returns `None` so
    it's dropped exactly like the baseline side drops it.
    """
    code = pitch_type_data.get("code")
    if isinstance(code, str) and code:
        normalized = code.upper()
    else:
        description = pitch_type_data.get("description")
        if not isinstance(description, str) or not description:
            return None
        normalized = _DESCRIPTION_TO_CODE.get(description.strip().lower(), description)
    return None if normalized in NON_ARSENAL_PITCH_TYPES else normalized
