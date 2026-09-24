"""Parsing helpers shared by `ScheduleSource` and `game_summary`.

MLB exposes the same `linescore` shape (`currentInning`, `isTopInning`,
`inningState`, `outs`, `defense.pitcher`) in two different places: nested
under `games[]` in the hydrated schedule response, and under
`liveData.linescore` in a game's own live feed. Both callers need the exact
same defensive parsing and the exact same "current pitcher only while live"
rule, so it lives here once instead of twice.
"""

from __future__ import annotations

from typing import Any, Literal

from ..schemas import PitcherRef

GameState = Literal["live", "upcoming", "final", "other"]


def parse_pitcher_ref(person: Any) -> PitcherRef | None:
    """Build a `PitcherRef` from an `{id, fullName}`-shaped object, or `None`."""
    if not isinstance(person, dict):
        return None
    person_id = person.get("id")
    name = person.get("fullName")
    if not isinstance(person_id, int) or not isinstance(name, str) or not name:
        return None
    return PitcherRef(id=person_id, name=name)


def game_state_from_status(status: Any) -> GameState:
    """Derive `GameSummary.state` from `gameData.status.abstractGameState`."""
    abstract_state = status.get("abstractGameState") if isinstance(status, dict) else None
    if abstract_state == "Live":
        return "live"
    if abstract_state == "Preview":
        return "upcoming"
    if abstract_state == "Final":
        return "final"
    return "other"


def linescore_fields(linescore: Any, state: GameState) -> dict[str, Any]:
    """Extract inning/outs/current-pitcher fields from a `linescore` object.

    Every field defaults to `None` — missing data is never turned into `0`.
    `current_pitcher`/`current_pitcher_team_side` are only ever populated
    when `state == "live"`: a Final game's `linescore.defense.pitcher` is
    just the last pitcher who threw, not a "current" one.
    """
    fields: dict[str, Any] = {
        "inning": None,
        "inning_half": None,
        "inning_state": None,
        "outs": None,
        "current_pitcher": None,
        "current_pitcher_team_side": None,
    }
    if not isinstance(linescore, dict):
        return fields

    inning = linescore.get("currentInning")
    if isinstance(inning, int):
        fields["inning"] = inning

    is_top_inning = linescore.get("isTopInning")
    if isinstance(is_top_inning, bool):
        fields["inning_half"] = "top" if is_top_inning else "bottom"

    inning_state = linescore.get("inningState")
    if isinstance(inning_state, str):
        fields["inning_state"] = inning_state

    outs = linescore.get("outs")
    if isinstance(outs, int):
        fields["outs"] = outs

    if state == "live" and isinstance(is_top_inning, bool):
        defense = linescore.get("defense")
        pitcher_ref = (
            parse_pitcher_ref(defense.get("pitcher")) if isinstance(defense, dict) else None
        )
        if pitcher_ref is not None:
            fields["current_pitcher"] = pitcher_ref
            # Top inning: away team bats, so the home team is on defense.
            fields["current_pitcher_team_side"] = "home" if is_top_inning else "away"

    return fields
