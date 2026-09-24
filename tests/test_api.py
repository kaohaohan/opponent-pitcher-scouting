"""API surface, wired to a throwaway database."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.api import routes
from app.db import get_session
from app.main import create_app
from app.sources import LiveSource, ScheduleSource


@pytest.fixture()
def client(session_factory, monkeypatch) -> Iterator[TestClient]:
    # The replay endpoint builds its own processor, so point it at the test db too.
    monkeypatch.setattr(routes, "SessionFactory", session_factory)
    # The startup hook would otherwise create the schema in the real database.
    monkeypatch.setattr(main, "create_all", lambda: None)

    app = create_app()

    def override_get_session():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_endpoints_are_empty_before_a_replay(client):
    assert client.get("/api/players").json() == []
    assert client.get("/api/events").json() == []
    assert client.get("/api/alerts").json() == []
    assert client.get("/api/pitch-mix-alerts").json() == []


def test_replay_endpoint_reports_what_it_ingested(client):
    response = client.post("/api/replay")

    assert response.status_code == 200
    assert response.json() == {
        "source": "replay",
        "events_read": 6,
        "stored": 5,
        "duplicates": 0,
        "ignored_incomplete": 1,
        "invalid": 0,
        "alerts_created": 3,
        "source_error": None,
    }


def test_replay_endpoint_is_idempotent(client):
    client.post("/api/replay")
    second = client.post("/api/replay").json()

    assert second["stored"] == 0
    assert second["duplicates"] == 5
    assert second["alerts_created"] == 0
    assert len(client.get("/api/events").json()) == 5


def test_reads_after_replay(client):
    client.post("/api/replay")

    players = client.get("/api/players").json()
    assert [player["name"] for player in players] == ["Hao-Yu Lee"]

    events = client.get("/api/events").json()
    assert [event["at_bat_index"] for event in events] == [1, 2, 3, 4, 5]
    # The incomplete plate appearance was never stored.
    assert all(event["is_complete"] for event in events)
    # Absent Statcast values survive the round trip as nulls.
    flyout = next(event for event in events if event["result"] == "Flyout")
    assert flyout["exit_velocity"] is None
    assert flyout["pitch_velocity"] is None

    alerts = client.get("/api/alerts").json()
    assert sorted(alert["rule_type"] for alert in alerts) == [
        "extra_base_hit",
        "hard_contact",
        "high_velocity_hit",
    ]


def test_events_can_be_filtered_by_player_and_game(client):
    client.post("/api/replay")
    player_id = client.get("/api/players").json()[0]["id"]

    assert len(client.get(f"/api/events?player_id={player_id}").json()) == 5
    assert client.get("/api/events?game_id=nope").json() == []


def test_alerts_can_be_filtered_by_rule_type(client):
    client.post("/api/replay")

    alerts = client.get("/api/alerts?rule_type=hard_contact").json()
    assert len(alerts) == 1
    assert "exit velocity" in alerts[0]["message"]


def test_alert_timestamps_are_serialized_with_a_utc_offset(client):
    """Without an offset, browsers read the time as local and show e.g.
    "8h ago" in Taiwan for an alert created seconds ago."""
    client.post("/api/replay")

    created_at = client.get("/api/alerts").json()[0]["created_at"]

    assert created_at.endswith(("Z", "+00:00"))


def test_replay_endpoint_reports_a_missing_fixture(client):
    response = client.post("/api/replay?fixture_path=/tmp/does-not-exist.json")

    assert response.status_code == 404


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_live_sync_endpoint_ingests_and_deduplicates_snapshot(client, monkeypatch):
    fixture = Path(__file__).parent / "fixtures" / "mlb_live_feed_776743_20250814_230000.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))

    def source_factory(game_id, batter_ids=(), pitcher_ids=()):
        return LiveSource(
            game_id,
            batter_ids=batter_ids,
            pitcher_ids=pitcher_ids,
            client=httpx.Client(transport=transport),
        )

    monkeypatch.setattr(routes, "LiveSource", source_factory)
    response = client.post(
        "/api/live/sync", json={"game_id": 776743, "watched_player_ids": [657557]}
    )

    assert response.status_code == 200
    assert response.json()["events_read"] == 3
    assert response.json()["stored"] == 2
    assert response.json()["invalid"] == 1
    assert response.json()["game_state"] == "Live"

    second = client.post(
        "/api/live/sync", json={"game_id": 776743, "watched_player_ids": [657557, 657557]}
    )
    assert second.status_code == 200
    assert second.json()["stored"] == 0
    assert second.json()["duplicates"] == 2
    assert len(client.get("/api/events?game_id=776743").json()) == 2


def test_live_sync_validates_request_before_fetch(client):
    response = client.post("/api/live/sync", json={"game_id": 0, "watched_player_ids": []})

    assert response.status_code == 422


def test_live_sync_accepts_pitcher_ids(client, monkeypatch):
    fixture = Path(__file__).parent / "fixtures" / "mlb_live_feed_776743_20250814_230000.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))

    def source_factory(game_id, batter_ids=(), pitcher_ids=()):
        return LiveSource(
            game_id,
            batter_ids=batter_ids,
            pitcher_ids=pitcher_ids,
            client=httpx.Client(transport=transport),
        )

    monkeypatch.setattr(routes, "LiveSource", source_factory)
    response = client.post("/api/live/sync", json={"game_id": 776743, "pitcher_ids": [701002]})

    assert response.status_code == 200
    body = response.json()
    assert body["events_read"] == 2
    assert body["stored"] == 2
    assert body["alerts_created"] == 0
    events = client.get("/api/events?pitcher_id=701002").json()
    assert [event["at_bat_index"] for event in events] == [6, 7]
    assert {event["pitcher_name"] for event in events} == {"Two-Way Reserve"}


def test_live_sync_can_add_missing_pitcher_alert_for_existing_pa(client, monkeypatch):
    fixture = Path(__file__).parent / "fixtures" / "mlb_live_feed_776743_20250814_230000.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))

    def source_factory(game_id, batter_ids=(), pitcher_ids=()):
        return LiveSource(
            game_id,
            batter_ids=batter_ids,
            pitcher_ids=pitcher_ids,
            client=httpx.Client(transport=transport),
        )

    monkeypatch.setattr(routes, "LiveSource", source_factory)
    client.post("/api/live/sync", json={"game_id": 776743, "batter_ids": [657557]})
    second = client.post("/api/live/sync", json={"game_id": 776743, "pitcher_ids": [542881]})
    third = client.post("/api/live/sync", json={"game_id": 776743, "pitcher_ids": [542881]})

    assert second.status_code == 200
    assert second.json()["stored"] == 0
    assert second.json()["duplicates"] == 1
    assert second.json()["alerts_created"] == 2
    assert third.json()["alerts_created"] == 0
    pitcher_alerts = client.get("/api/alerts?subject_role=pitcher").json()
    assert sorted(alert["rule_type"] for alert in pitcher_alerts) == [
        "pitcher_extra_base_hit_allowed",
        "pitcher_high_exit_velocity_allowed",
    ]


def test_game_participants_endpoint(client, monkeypatch):
    fixture = Path(__file__).parent / "fixtures" / "mlb_live_feed_776743_20250814_230000.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))

    def source_factory(game_id):
        return LiveSource(game_id, client=httpx.Client(transport=transport))

    monkeypatch.setattr(routes, "LiveSource", source_factory)
    response = client.get("/api/live/games/776743/participants")

    assert response.status_code == 200
    body = response.json()
    assert body["teams"]["away"]["id"] == 145
    assert body["participants"]
    by_id = {participant["player_id"]: participant for participant in body["participants"]}
    assert by_id[657557]["roles"] == ["batter"]
    assert by_id[542881]["roles"] == ["pitcher"]
    assert by_id[701002]["roles"] == ["batter", "pitcher"]
    assert client.get("/api/players").json() == []


def test_live_game_summary_endpoint_returns_game_summary(client, monkeypatch):
    payload = {
        "gamePk": 776743,
        "gameData": {
            "status": {"abstractGameState": "Live", "detailedState": "In Progress"},
            "teams": {
                "away": {"id": 145, "name": "Chicago White Sox"},
                "home": {"id": 108, "name": "Los Angeles Angels"},
            },
            "datetime": {"dateTime": "2025-08-14T23:00:00Z", "officialDate": "2025-08-14"},
            "probablePitchers": {},
        },
        "liveData": {
            "plays": {"allPlays": []},
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
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))

    def source_factory(game_id):
        return LiveSource(game_id, client=httpx.Client(transport=transport))

    monkeypatch.setattr(routes, "LiveSource", source_factory)
    response = client.get("/api/live/games/776743/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["game_id"] == "776743"
    assert body["state"] == "live"
    assert body["away_score"] == 2
    assert body["home_score"] == 1
    assert body["inning"] == 5
    assert body["inning_half"] == "top"
    assert body["outs"] == 1
    assert body["current_pitcher"] == {"id": 542881, "name": "Tyler Anderson"}
    assert body["current_pitcher_team_side"] == "home"


def test_live_game_summary_endpoint_reports_game_not_found(client, monkeypatch):
    transport = httpx.MockTransport(lambda request: httpx.Response(404))

    def source_factory(game_id):
        return LiveSource(game_id, client=httpx.Client(transport=transport))

    monkeypatch.setattr(routes, "LiveSource", source_factory)
    response = client.get("/api/live/games/999999/summary")

    assert response.status_code == 404


def test_live_game_summary_endpoint_reports_upstream_failure(client, monkeypatch):
    def raise_transport(request):
        raise httpx.ConnectError("boom", request=request)

    transport = httpx.MockTransport(raise_transport)

    def source_factory(game_id):
        return LiveSource(game_id, client=httpx.Client(transport=transport))

    monkeypatch.setattr(routes, "LiveSource", source_factory)
    response = client.get("/api/live/games/776743/summary")

    assert response.status_code == 502


def test_live_games_endpoint_returns_schedule_for_date(client, monkeypatch):
    payload = {
        "dates": [
            {
                "date": "2025-08-14",
                "games": [
                    {
                        "gamePk": 776750,
                        "gameDate": "2025-08-14T17:05:00Z",
                        "status": {"abstractGameState": "Final", "detailedState": "Final"},
                        "teams": {
                            "away": {"team": {"id": 136, "name": "Seattle Mariners"}, "score": 3},
                            "home": {"team": {"id": 110, "name": "Baltimore Orioles"}, "score": 5},
                        },
                    }
                ],
            }
        ]
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    monkeypatch.setattr(
        routes,
        "ScheduleSource",
        lambda: ScheduleSource(client=httpx.Client(transport=transport)),
    )
    response = client.get("/api/live/games", params={"date": "2025-08-14"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["game_id"] == "776750"
    assert body[0]["away_team"]["name"] == "Seattle Mariners"
    assert body[0]["home_team"]["name"] == "Baltimore Orioles"
    assert body[0]["status"] == "Final"
    assert body[0]["state"] == "final"
    assert body[0]["away_score"] == 3
    assert body[0]["home_score"] == 5
    assert body[0]["current_pitcher"] is None


def test_live_games_endpoint_returns_empty_list_when_no_games(client, monkeypatch):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"dates": []}))
    monkeypatch.setattr(
        routes,
        "ScheduleSource",
        lambda: ScheduleSource(client=httpx.Client(transport=transport)),
    )

    response = client.get("/api/live/games", params={"date": "2025-08-14"})

    assert response.status_code == 200
    assert response.json() == []


def test_live_games_endpoint_reports_upstream_failure(client, monkeypatch):
    def raise_transport(request):
        raise httpx.ConnectError("boom", request=request)

    transport = httpx.MockTransport(raise_transport)
    monkeypatch.setattr(
        routes,
        "ScheduleSource",
        lambda: ScheduleSource(client=httpx.Client(transport=transport)),
    )

    response = client.get("/api/live/games", params={"date": "2025-08-14"})

    assert response.status_code == 502


def test_live_games_endpoint_validates_date_format(client):
    response = client.get("/api/live/games", params={"date": "not-a-date"})

    assert response.status_code == 400
