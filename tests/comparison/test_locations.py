"""Today-only pitch locations from the live feed."""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app import main
from app.comparison import api as comparison_api
from app.comparison.locations import compute_pitch_locations
from app.main import create_app
from app.sources.live import LiveFeedError, LiveGameNotFound
from tests.comparison.fakes import StubLiveSource


@pytest.fixture()
def client(monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setattr(main, "create_all", lambda: None)
    with TestClient(create_app()) as test_client:
        yield test_client


def event(code: str, x: object = 0, z: object = 2.5, top: object = 3.5,
          bottom: object = 1.5) -> dict:
    return {
        "isPitch": True,
        "details": {"type": {"code": code}},
        "pitchData": {
            "coordinates": {"pX": x, "pZ": z},
            "strikeZoneTop": top,
            "strikeZoneBottom": bottom,
        },
    }


def payload() -> dict:
    return {"liveData": {"plays": {"allPlays": [
        {"matchup": {"pitcher": {"id": 123}}, "playEvents": [
            event("FF"), event("SL", x=-1.3, z=4.2),
            event("CU", x=None), event("CH", top=2, bottom=2),
            event("SI", x=float("inf")), event("PO"),
            {"isPitch": False, "details": {"type": {"code": "FF"}}},
        ]},
        # An unfinished plate appearance still has valid pitches.
        {"matchup": {"pitcher": {"id": 123}}, "playEvents": [
            {"isPitch": True, "details": {"type": {"description": "Four-Seam Fastball"}},
             "pitchData": {"coordinates": {"pX": 0.2, "pZ": 2.4},
                           "strikeZoneTop": 3.3, "strikeZoneBottom": 1.4}},
        ]},
        {"matchup": {"pitcher": {"id": 999}}, "playEvents": [event("FF")]},
    ]}}}


def test_counts_typed_pitches_and_preserves_zero_and_out_of_zone():
    result = compute_pitch_locations(payload(), 123)
    assert result.total_pitches == 6
    assert [point.pitch_type for point in result.points] == ["FF", "SL", "FF"]
    assert result.points[0].plate_x == 0
    assert result.points[1].plate_x == -1.3
    assert result.points[1].plate_z > result.points[1].sz_top


def test_missing_and_invalid_numbers_are_omitted_from_points():
    feed = deepcopy(payload())
    events = feed["liveData"]["plays"]["allPlays"][0]["playEvents"]
    events.extend([event("FF", x=True), event("SL", z=float("nan")),
                   event("CU", top=None), event("CH", top=1, bottom=2)])
    result = compute_pitch_locations(feed, 123)
    assert result.total_pitches == 10
    assert len(result.points) == 3


def test_locations_route_is_independent_of_statcast(client, monkeypatch):
    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(payload()))
    response = client.get("/api/live/games/777/pitchers/123/locations")
    assert response.status_code == 200
    assert response.json()["total_pitches"] == 6
    assert len(response.json()["points"]) == 3
    assert client.get("/api/live/games/777/pitchers/9999/locations").json() == {
        "total_pitches": 0, "points": []}


def test_locations_route_preserves_live_source_errors(client, monkeypatch):
    for error, expected in [(LiveGameNotFound("missing"), 404),
                            (LiveFeedError("feed down"), 502)]:
        monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(error=error))
        assert client.get("/api/live/games/777/pitchers/123/locations").status_code == expected
