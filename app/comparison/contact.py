"""Contact pitch cards: the specific pitches, in this outing, that ended
in a home run or in contact hit at 100+ mph exit velocity.

Selection mirrors `app.comparison.outcomes.compute_pitcher_outcome_context`
exactly (same completed-play filter, same pitcher-id match, same terminal-
pitch pick) so the two stay consistent: the number of `high_ev_contact`
cards here always equals that module's `hard_hit_contacts` count, and the
number of `home_run` cards always equals its `home_runs_allowed` count, for
the same payload and pitcher. This module only decides *which* pitches to
surface as cards and *what facts* to attach to each one — it draws no
conclusion about whether the pitch was well- or poorly-executed.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ..rules.engine import HARD_CONTACT_EXIT_VELOCITY_MPH
from .live_metrics import _normalize_pitch_type
from .locations import _finite_number
from .outcomes import exit_velocity_from_hit_data
from .regions import Region, classify_region

ContactReason = Literal["home_run", "high_ev_contact"]


class ContactPitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at_bat_index: int | None
    inning: int | None
    batter_name: str | None
    reasons: list[ContactReason]
    outcome: str | None
    pitch_type: str | None
    pitch_velocity_mph: float | None
    balls: int | None
    strikes: int | None
    batter_side: Literal["L", "R"] | None
    plate_x: float | None
    plate_z: float | None
    sz_top: float | None
    sz_bot: float | None
    region: Region | None
    exit_velocity_mph: float | None
    launch_angle_deg: float | None


class ContactPitches(BaseModel):
    model_config = ConfigDict(extra="forbid")

    high_ev_threshold_mph: float
    pitches: list[ContactPitch]


def _terminal_pitch_event(play: dict[str, Any]) -> dict[str, Any] | None:
    events = play.get("playEvents")
    if not isinstance(events, list):
        return None
    for event in reversed(events):
        if isinstance(event, dict) and event.get("isPitch") is True:
            return event
    return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _batter_side(matchup: dict[str, Any]) -> Literal["L", "R"] | None:
    bat_side = matchup.get("batSide")
    code = bat_side.get("code") if isinstance(bat_side, dict) else None
    return code if code in ("L", "R") else None


def compute_contact_pitches(payload: dict[str, Any], pitcher_id: int) -> ContactPitches:
    """This pitcher's home-run and 100+ mph exit-velocity contact pitches
    for the game, in at-bat order.

    A card is included when the completed play's result was a home run
    and/or its terminal pitch's exit velocity was at or above
    `HARD_CONTACT_EXIT_VELOCITY_MPH` (a card can carry both reasons at
    once, e.g. a home run measured at 100+ mph). Every other field is
    best-effort: a value that can't be read from the feed is `None`, never
    a substituted `0`.
    """
    plays = payload.get("liveData", {}).get("plays", {}).get("allPlays", [])
    if not isinstance(plays, list):
        plays = []

    cards: list[ContactPitch] = []
    for play in plays:
        if not isinstance(play, dict):
            continue
        about = play.get("about")
        matchup = play.get("matchup")
        if not isinstance(about, dict) or about.get("isComplete") is not True:
            continue
        if not isinstance(matchup, dict):
            continue
        pitcher = matchup.get("pitcher")
        if not isinstance(pitcher, dict) or str(pitcher.get("id")) != str(pitcher_id):
            continue

        result = play.get("result")
        # Selection mirrors `compute_pitcher_outcome_context`, which keys home
        # runs off `result.event` (this repo's live-feed fixtures carry no
        # `result.eventType`), so both modules agree on what counts as one.
        result_event = result.get("event") if isinstance(result, dict) else None
        is_home_run = result_event == "Home Run"

        terminal = _terminal_pitch_event(play)
        hit_data = terminal.get("hitData") if isinstance(terminal, dict) else None
        exit_velocity = exit_velocity_from_hit_data(hit_data)
        is_high_ev = exit_velocity is not None and exit_velocity >= HARD_CONTACT_EXIT_VELOCITY_MPH

        reasons: list[ContactReason] = []
        if is_home_run:
            reasons.append("home_run")
        if is_high_ev:
            reasons.append("high_ev_contact")
        if not reasons:
            continue

        batter = matchup.get("batter") if isinstance(matchup.get("batter"), dict) else {}
        batter_name = batter.get("fullName") if isinstance(batter.get("fullName"), str) else None

        details = terminal.get("details") if isinstance(terminal, dict) else None
        pitch_type_data = details.get("type") if isinstance(details, dict) else None
        pitch_type = _normalize_pitch_type(
            pitch_type_data if isinstance(pitch_type_data, dict) else {}
        )

        pitch_data = terminal.get("pitchData") if isinstance(terminal, dict) else None
        pitch_data = pitch_data if isinstance(pitch_data, dict) else {}
        pitch_velocity_mph = _finite_number(pitch_data.get("startSpeed"))
        if pitch_velocity_mph is not None and pitch_velocity_mph <= 0:
            pitch_velocity_mph = None

        coordinates = pitch_data.get("coordinates")
        coordinates = coordinates if isinstance(coordinates, dict) else {}
        plate_x = _finite_number(coordinates.get("pX"))
        plate_z = _finite_number(coordinates.get("pZ"))
        sz_top = _finite_number(pitch_data.get("strikeZoneTop"))
        sz_bot = _finite_number(pitch_data.get("strikeZoneBottom"))
        region = classify_region(plate_x, plate_z, sz_top, sz_bot)

        count = terminal.get("count") if isinstance(terminal, dict) else None
        count = count if isinstance(count, dict) else {}
        balls = _int_or_none(count.get("balls"))
        strikes = _int_or_none(count.get("strikes"))

        launch_angle_deg = None
        if isinstance(hit_data, dict):
            raw_launch_angle = hit_data.get("launchAngle")
            if isinstance(raw_launch_angle, int | float) and not isinstance(
                raw_launch_angle, bool
            ):
                candidate = float(raw_launch_angle)
                launch_angle_deg = candidate if math.isfinite(candidate) else None

        cards.append(
            ContactPitch(
                at_bat_index=_int_or_none(about.get("atBatIndex")),
                inning=_int_or_none(about.get("inning")),
                batter_name=batter_name,
                reasons=reasons,
                outcome=result_event,
                pitch_type=pitch_type,
                pitch_velocity_mph=pitch_velocity_mph,
                balls=balls,
                strikes=strikes,
                batter_side=_batter_side(matchup),
                plate_x=plate_x,
                plate_z=plate_z,
                sz_top=sz_top,
                sz_bot=sz_bot,
                region=region,
                exit_velocity_mph=exit_velocity,
                launch_angle_deg=launch_angle_deg,
            )
        )

    cards.sort(key=lambda card: card.at_bat_index if card.at_bat_index is not None else 10**9)
    return ContactPitches(high_ev_threshold_mph=HARD_CONTACT_EXIT_VELOCITY_MPH, pitches=cards)
