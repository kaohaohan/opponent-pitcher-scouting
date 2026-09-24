"""Pure builder: one MLB live feed payload -> `GameSummary`.

`LiveSource.fetch_snapshot` already fetches this exact payload (shared, via
its TTL cache, with Phase 3/4 event ingestion and the Phase 5 comparison
route); this module reads the scoreboard-level detail out of it — status,
score, inning, current pitcher, probable pitchers, each team's pitchers
used — that the plate-appearance pipeline discards. It reuses
`app.sources._linescore`'s parsing helpers rather than re-implementing them,
since a live feed's `liveData.linescore` has the exact same shape as the
schedule endpoint's hydrated `linescore`.

No I/O here: this is a pure function of the payload dict to a `GameSummary`.
"""

from __future__ import annotations

from typing import Any

from ..schemas import GameSummary, PitcherRef, TeamRead
from ._linescore import game_state_from_status, linescore_fields, parse_pitcher_ref


def summarize_live_feed(payload: dict[str, Any]) -> GameSummary:
    """Build a `GameSummary` from one game's live feed payload.

    Assumes the payload already passed `LiveSource`'s own validation (it has
    `gameData.status`/`gameData.teams`), since callers always get this from
    `LiveSource.fetch_snapshot()`. Every other field degrades to `None` when
    absent rather than being defaulted to `0`.
    """
    game_data = payload.get("gameData") if isinstance(payload.get("gameData"), dict) else {}
    live_data = payload.get("liveData") if isinstance(payload.get("liveData"), dict) else {}

    status = game_data.get("status") if isinstance(game_data.get("status"), dict) else {}
    teams = game_data.get("teams") if isinstance(game_data.get("teams"), dict) else {}
    away_team = teams.get("away") if isinstance(teams.get("away"), dict) else {}
    home_team = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    datetime_data = (
        game_data.get("datetime") if isinstance(game_data.get("datetime"), dict) else {}
    )
    probable_pitchers = (
        game_data.get("probablePitchers")
        if isinstance(game_data.get("probablePitchers"), dict)
        else {}
    )

    boxscore = live_data.get("boxscore") if isinstance(live_data.get("boxscore"), dict) else {}
    boxscore_teams = boxscore.get("teams") if isinstance(boxscore.get("teams"), dict) else {}

    linescore = live_data.get("linescore") if isinstance(live_data.get("linescore"), dict) else {}
    linescore_teams = (
        linescore.get("teams") if isinstance(linescore.get("teams"), dict) else {}
    )

    game_pk = payload.get("gamePk")
    state = game_state_from_status(status)

    return GameSummary(
        game_id=str(game_pk) if game_pk is not None else "",
        game_date=str(datetime_data.get("officialDate") or ""),
        start_time=(
            str(datetime_data["dateTime"])
            if isinstance(datetime_data.get("dateTime"), str)
            else None
        ),
        status=status.get("detailedState") or status.get("abstractGameState") or "Unknown",
        state=state,
        away_team=TeamRead(id=away_team.get("id"), name=away_team.get("name") or "Unknown"),
        home_team=TeamRead(id=home_team.get("id"), name=home_team.get("name") or "Unknown"),
        away_score=_runs(linescore_teams.get("away")),
        home_score=_runs(linescore_teams.get("home")),
        probable_pitchers={
            "away": parse_pitcher_ref(probable_pitchers.get("away")),
            "home": parse_pitcher_ref(probable_pitchers.get("home")),
        },
        pitchers_used={
            "away": _pitchers_used(boxscore_teams.get("away")),
            "home": _pitchers_used(boxscore_teams.get("home")),
        },
        **linescore_fields(linescore, state),
    )


def _runs(team_linescore: Any) -> int | None:
    if not isinstance(team_linescore, dict):
        return None
    runs = team_linescore.get("runs")
    return runs if isinstance(runs, int) else None


def _pitchers_used(team_boxscore: Any) -> list[PitcherRef]:
    """A team's pitchers in order of appearance, from its boxscore.

    `teams.<side>.pitchers` is MLB's ordered list of pitcher ids; names come
    from the same team's `players["ID<id>"].person`. An id without a
    resolvable name is skipped rather than guessed at.
    """
    if not isinstance(team_boxscore, dict):
        return []
    pitcher_ids = team_boxscore.get("pitchers")
    players = team_boxscore.get("players")
    if not isinstance(pitcher_ids, list) or not isinstance(players, dict):
        return []
    used: list[PitcherRef] = []
    for pitcher_id in pitcher_ids:
        player = players.get(f"ID{pitcher_id}")
        person = player.get("person") if isinstance(player, dict) else None
        pitcher = parse_pitcher_ref(person)
        if pitcher is not None:
            used.append(pitcher)
    return used
