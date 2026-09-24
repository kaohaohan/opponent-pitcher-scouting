"""Deterministic tests for `summarize_live_feed`: live feed payload -> GameSummary."""

from __future__ import annotations

from app.sources.game_summary import summarize_live_feed


def _payload(**overrides):
    payload = {
        "gamePk": 776743,
        "gameData": {
            "status": {"abstractGameState": "Live", "detailedState": "In Progress"},
            "teams": {
                "away": {"id": 145, "name": "Chicago White Sox"},
                "home": {"id": 108, "name": "Los Angeles Angels"},
            },
            "datetime": {
                "dateTime": "2025-08-14T23:00:00Z",
                "officialDate": "2025-08-14",
            },
            "probablePitchers": {
                "away": {"id": 111, "fullName": "Away Probable"},
                "home": {"id": 222, "fullName": "Home Probable"},
            },
        },
        "liveData": {
            "linescore": {
                "currentInning": 5,
                "isTopInning": True,
                "inningState": "Top",
                "outs": 1,
                "defense": {"pitcher": {"id": 542881, "fullName": "Tyler Anderson"}},
                "teams": {"away": {"runs": 2}, "home": {"runs": 1}},
            }
        },
    }
    payload.update(overrides)
    return payload


def test_summarize_live_feed_reports_live_game_current_pitcher_and_inning_state():
    summary = summarize_live_feed(_payload())

    assert summary.game_id == "776743"
    assert summary.game_date == "2025-08-14"
    assert summary.start_time == "2025-08-14T23:00:00Z"
    assert summary.status == "In Progress"
    assert summary.state == "live"
    assert summary.away_team.name == "Chicago White Sox"
    assert summary.home_team.name == "Los Angeles Angels"
    assert summary.away_score == 2
    assert summary.home_score == 1
    assert summary.inning == 5
    assert summary.inning_half == "top"
    assert summary.inning_state == "Top"
    assert summary.outs == 1
    assert summary.current_pitcher is not None
    assert summary.current_pitcher.id == 542881
    assert summary.current_pitcher.name == "Tyler Anderson"
    # Top inning: away team bats, home team is on defense.
    assert summary.current_pitcher_team_side == "home"
    assert summary.probable_pitchers["away"].id == 111
    assert summary.probable_pitchers["home"].id == 222


def test_summarize_live_feed_final_game_never_reports_a_current_pitcher():
    payload = _payload()
    payload["gameData"]["status"] = {"abstractGameState": "Final", "detailedState": "Final"}
    payload["liveData"]["linescore"]["isTopInning"] = False
    # A Final game's linescore.defense.pitcher is just the last pitcher who
    # threw, not a "current" one — it must not be surfaced.
    payload["liveData"]["linescore"]["defense"] = {
        "pitcher": {"id": 999, "fullName": "Last Pitcher"}
    }

    summary = summarize_live_feed(payload)

    assert summary.state == "final"
    assert summary.status == "Final"
    assert summary.current_pitcher is None
    assert summary.current_pitcher_team_side is None
    # Non-pitcher inning detail still comes through for a final game.
    assert summary.inning == 5
    assert summary.outs == 1


def test_summarize_live_feed_upcoming_game_has_no_linescore_yet():
    payload = _payload()
    payload["gameData"]["status"] = {"abstractGameState": "Preview", "detailedState": "Scheduled"}
    payload["liveData"] = {}

    summary = summarize_live_feed(payload)

    assert summary.state == "upcoming"
    assert summary.away_score is None
    assert summary.home_score is None
    assert summary.inning is None
    assert summary.inning_half is None
    assert summary.outs is None
    assert summary.current_pitcher is None
    # Probable pitchers still come from gameData, independent of linescore.
    assert summary.probable_pitchers["away"].id == 111
    assert summary.probable_pitchers["home"].id == 222


def test_summarize_live_feed_lists_each_teams_pitchers_in_order_of_appearance():
    payload = _payload()
    payload["liveData"]["boxscore"] = {
        "teams": {
            "away": {
                "pitchers": [111, 333],
                "players": {
                    "ID111": {"person": {"id": 111, "fullName": "Away Starter"}},
                    "ID333": {"person": {"id": 333, "fullName": "Away Reliever"}},
                },
            },
            "home": {
                "pitchers": [542881],
                "players": {"ID542881": {"person": {"id": 542881, "fullName": "Tyler Anderson"}}},
            },
        }
    }

    summary = summarize_live_feed(payload)

    assert [p.name for p in summary.pitchers_used["away"]] == ["Away Starter", "Away Reliever"]
    assert [p.id for p in summary.pitchers_used["home"]] == [542881]


def test_summarize_live_feed_without_boxscore_has_no_pitchers_used():
    summary = summarize_live_feed(_payload())

    assert summary.pitchers_used == {"away": [], "home": []}
