"""Deterministic in-game outcomes for the selected pitcher."""

from __future__ import annotations

import math
from typing import Any

from ..rules.engine import HARD_CONTACT_EXIT_VELOCITY_MPH
from .schemas import OutcomeContext


def exit_velocity_from_hit_data(hit_data: Any) -> float | None:
    """Parse a terminal pitch event's `hitData.launchSpeed` into a finite,
    positive exit velocity, or `None` when it's missing, unparseable,
    non-finite, or not a real reading (<= 0).
    """
    raw_exit_velocity = hit_data.get("launchSpeed") if isinstance(hit_data, dict) else None
    try:
        exit_velocity = float(raw_exit_velocity)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(exit_velocity) or exit_velocity <= 0:
        return None
    return exit_velocity


def compute_pitcher_outcome_context(
    payload: dict[str, Any], pitcher_id: int
) -> OutcomeContext:
    """Summarize completed plate appearances attributed to one pitcher.

    Counts are descriptive game totals. Hard-hit contact uses the same 100 mph
    exit-velocity threshold as the existing pitcher alert rule.
    """
    plays = payload.get("liveData", {}).get("plays", {}).get("allPlays", [])
    if not isinstance(plays, list):
        plays = []

    completed = home_runs = extra_base_hits = hard_hits = measured = 0
    max_exit_velocity: float | None = None
    for play in plays:
        if not isinstance(play, dict):
            continue
        about = play.get("about")
        matchup = play.get("matchup")
        if not isinstance(about, dict) or about.get("isComplete") is not True:
            continue
        pitcher = matchup.get("pitcher") if isinstance(matchup, dict) else None
        if not isinstance(pitcher, dict) or str(pitcher.get("id")) != str(pitcher_id):
            continue

        completed += 1
        result = play.get("result")
        result_name = result.get("event") if isinstance(result, dict) else None
        if result_name == "Home Run":
            home_runs += 1
        if result_name in {"Double", "Triple", "Home Run"}:
            extra_base_hits += 1

        events = play.get("playEvents")
        pitches = (
            (
                event
                for event in reversed(events)
                if isinstance(event, dict) and event.get("isPitch") is True
            )
            if isinstance(events, list)
            else ()
        )
        terminal = next(pitches, None)
        hit_data = terminal.get("hitData") if isinstance(terminal, dict) else None
        exit_velocity = exit_velocity_from_hit_data(hit_data)
        if exit_velocity is None:
            continue
        measured += 1
        if exit_velocity >= HARD_CONTACT_EXIT_VELOCITY_MPH:
            hard_hits += 1
        if max_exit_velocity is None or exit_velocity > max_exit_velocity:
            max_exit_velocity = exit_velocity

    limitations = []
    if completed == 0:
        limitations.append("No completed plate appearances for this pitcher are available yet.")
    if measured < completed:
        limitations.append("Exit velocity is unavailable for some completed plate appearances.")

    return OutcomeContext(
        completed_plate_appearances=completed,
        home_runs_allowed=home_runs,
        extra_base_hits_allowed=extra_base_hits,
        hard_hit_contacts=hard_hits,
        hard_hit_threshold_mph=HARD_CONTACT_EXIT_VELOCITY_MPH,
        measured_exit_velocity_count=measured,
        max_exit_velocity_mph=max_exit_velocity,
        limitations=limitations,
    )
