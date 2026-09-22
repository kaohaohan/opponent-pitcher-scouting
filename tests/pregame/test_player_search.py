"""Pitcher name search: pure-function payload normalization, plus the HTTP
endpoint wired to a fake source. No live MLB calls."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import create_app
from app.pregame.api import get_pitcher_search_source
from app.pregame.schemas import PitcherSearchResult
from app.pregame.sources.player_search import parse_people
from tests.pregame.fakes import FakePitcherSearchSource


def make_person(
    player_id: int = 543037,
    name: str = "Gerrit Cole",
    position_type: str = "Pitcher",
    team: str | None = "New York Yankees",
    throws: str | None = "R",
) -> dict:
    person: dict = {
        "id": player_id,
        "fullName": name,
        "primaryPosition": {"type": position_type},
    }
    if team is not None:
        person["currentTeam"] = {"id": 147, "name": team}
    if throws is not None:
        person["pitchHand"] = {"code": throws}
    return person


def test_parse_people_normalizes_a_pitcher_row():
    payload = {"people": [make_person()]}

    results = parse_people(payload)

    assert results == [
        PitcherSearchResult(id=543037, name="Gerrit Cole", team="New York Yankees", throws="R")
    ]


def test_parse_people_includes_two_way_players():
    payload = {
        "people": [
            make_person(player_id=660271, name="Shohei Ohtani", position_type="Two-Way Player")
        ]
    }

    results = parse_people(payload)

    assert len(results) == 1
    assert results[0].name == "Shohei Ohtani"


def test_parse_people_excludes_non_pitchers():
    payload = {"people": [make_person(position_type="Outfielder")]}

    assert parse_people(payload) == []


def test_parse_people_tolerates_missing_team_and_throws():
    payload = {"people": [make_person(team=None, throws=None)]}

    results = parse_people(payload)

    assert results == [PitcherSearchResult(id=543037, name="Gerrit Cole", team=None, throws=None)]


def test_parse_people_skips_malformed_rows():
    payload = {"people": [{"primaryPosition": {"type": "Pitcher"}}]}

    assert parse_people(payload) == []


def test_parse_people_handles_empty_results():
    assert parse_people({"people": []}) == []


def test_parse_people_handles_unexpected_shapes():
    assert parse_people({}) == []
    assert parse_people(None) == []


@pytest.fixture()
def client(monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setattr(main, "create_all", lambda: None)
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_search_endpoint_returns_matches_from_the_source(client):
    fake_source = FakePitcherSearchSource(
        [PitcherSearchResult(id=543037, name="Gerrit Cole", team="New York Yankees", throws="R")]
    )
    client.app.dependency_overrides[get_pitcher_search_source] = lambda: fake_source

    response = client.get("/api/pregame/pitchers/search", params={"query": "cole"})

    assert response.status_code == 200
    assert response.json() == [
        {"id": 543037, "name": "Gerrit Cole", "team": "New York Yankees", "throws": "R"}
    ]
    assert fake_source.received_queries == ["cole"]


def test_search_endpoint_rejects_a_too_short_query(client):
    response = client.get("/api/pregame/pitchers/search", params={"query": "a"})

    assert response.status_code == 422


def test_search_endpoint_reports_a_search_failure_as_a_clear_error(client):
    from app.pregame.sources.player_search import PitcherSearchError

    def broken_source():
        class BrokenSource:
            name = "broken"

            def search(self, query: str):
                raise PitcherSearchError("upstream is down")

        return BrokenSource()

    client.app.dependency_overrides[get_pitcher_search_source] = broken_source
    response = client.get("/api/pregame/pitchers/search", params={"query": "cole"})

    assert response.status_code == 502
    assert "upstream is down" in response.json()["detail"]
