"""API surface, wired to a throwaway database."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import main
from app.api import routes
from app.db import get_session
from app.main import create_app


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


def test_replay_endpoint_reports_a_missing_fixture(client):
    response = client.post("/api/replay?fixture_path=/tmp/does-not-exist.json")

    assert response.status_code == 404


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
