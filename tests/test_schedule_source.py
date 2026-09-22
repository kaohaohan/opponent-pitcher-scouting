"""Deterministic tests for the MLB schedule adapter."""

from __future__ import annotations

import httpx
import pytest

from app.sources import ScheduleSource, ScheduleSourceError


def _source(payload, status_code=200):
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code, json=payload))
    return ScheduleSource(client=httpx.Client(transport=transport))


def _schedule_payload(games):
    return {"dates": [{"date": "2025-08-14", "games": games}]}


def test_games_for_date_maps_teams_and_scores():
    payload = _schedule_payload(
        [
            {
                "gamePk": 776750,
                "gameDate": "2025-08-14T17:05:00Z",
                "status": {"abstractGameState": "Final", "detailedState": "Final"},
                "teams": {
                    "away": {"team": {"id": 136, "name": "Seattle Mariners"}, "score": 3},
                    "home": {"team": {"id": 110, "name": "Baltimore Orioles"}, "score": 5},
                },
            }
        ]
    )

    games = _source(payload).games_for_date("2025-08-14")

    assert len(games) == 1
    game = games[0]
    assert game.game_id == "776750"
    assert game.game_date == "2025-08-14"
    assert game.away_team.id == 136
    assert game.away_team.name == "Seattle Mariners"
    assert game.home_team.name == "Baltimore Orioles"
    assert game.status == "Final"
    assert game.start_time == "2025-08-14T17:05:00Z"
    assert game.away_score == 3
    assert game.home_score == 5


@pytest.mark.parametrize(
    "detailed_state, expected",
    [("Scheduled", "Scheduled"), ("In Progress", "In Progress"), ("Final", "Final")],
)
def test_games_for_date_maps_scheduled_live_final_status(detailed_state, expected):
    payload = _schedule_payload(
        [
            {
                "gamePk": 1,
                "gameDate": "2025-08-14T23:05:00Z",
                "status": {"abstractGameState": expected, "detailedState": detailed_state},
                "teams": {
                    "away": {"team": {"id": 1, "name": "Away Team"}},
                    "home": {"team": {"id": 2, "name": "Home Team"}},
                },
            }
        ]
    )

    games = _source(payload).games_for_date("2025-08-14")

    assert games[0].status == expected
    # No score reported yet for a scheduled or live game without a score key.
    if detailed_state == "Scheduled":
        assert games[0].away_score is None
        assert games[0].home_score is None


def test_games_for_date_returns_empty_list_for_no_games():
    payload = {"dates": []}

    games = _source(payload).games_for_date("2025-08-14")

    assert games == []


def test_games_for_date_raises_on_upstream_http_error():
    source = _source({}, status_code=502)

    with pytest.raises(ScheduleSourceError):
        source.games_for_date("2025-08-14")


def test_games_for_date_raises_on_network_failure():
    def raise_transport(request):
        raise httpx.ConnectError("boom", request=request)

    client = httpx.Client(transport=httpx.MockTransport(raise_transport))
    source = ScheduleSource(client=client)

    with pytest.raises(ScheduleSourceError):
        source.games_for_date("2025-08-14")


def test_games_for_date_skips_malformed_game_entries():
    payload = _schedule_payload(
        [
            {"gamePk": 1, "teams": {}},  # missing team names
            "not-a-game",
        ]
    )

    games = _source(payload).games_for_date("2025-08-14")

    assert games == []
