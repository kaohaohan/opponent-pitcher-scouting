"""Contact pitch cards: home runs and 100+ mph exit-velocity contact."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import main
from app.comparison import api as comparison_api
from app.comparison.contact import compute_contact_pitches
from app.comparison.outcomes import compute_pitcher_outcome_context
from app.main import create_app
from app.sources.live import LiveFeedError, LiveGameNotFound
from tests.comparison.fakes import StubLiveSource


@pytest.fixture()
def client(monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setattr(main, "create_all", lambda: None)
    with TestClient(create_app()) as test_client:
        yield test_client


def _play(
    *,
    pitcher_id: int = 542881,
    at_bat_index: int = 0,
    inning: int = 1,
    batter_name: str | None = "Test Batter",
    result: str = "Flyout",
    exit_velocity: object = None,
    launch_angle: object = None,
    complete: bool = True,
    pitch_type_code: str | None = "FF",
    start_speed: object = 95.0,
    plate_x: object = 0,
    plate_z: object = 2.5,
    sz_top: object = 3.5,
    sz_bot: object = 1.5,
    balls: object = 1,
    strikes: object = 2,
    bat_side: str | None = "R",
    include_hit_data: bool = True,
) -> dict:
    hit_data = {}
    if include_hit_data:
        if exit_velocity is not None:
            hit_data["launchSpeed"] = exit_velocity
        if launch_angle is not None:
            hit_data["launchAngle"] = launch_angle

    matchup: dict = {"pitcher": {"id": pitcher_id}, "batter": {"fullName": batter_name}}
    if bat_side is not None:
        matchup["batSide"] = {"code": bat_side}

    terminal_event = {
        "isPitch": True,
        "details": {"type": {"code": pitch_type_code}} if pitch_type_code else {},
        "pitchData": {
            "startSpeed": start_speed,
            "coordinates": {"pX": plate_x, "pZ": plate_z},
            "strikeZoneTop": sz_top,
            "strikeZoneBottom": sz_bot,
        },
        "hitData": hit_data,
        "count": {"balls": balls, "strikes": strikes},
    }
    return {
        "about": {"isComplete": complete, "atBatIndex": at_bat_index, "inning": inning},
        "matchup": matchup,
        "result": {"event": result},
        "playEvents": [terminal_event],
    }


def test_home_run_with_exit_velocity():
    payload = {"liveData": {"plays": {"allPlays": [
        _play(result="Home Run", exit_velocity=108.6, launch_angle=28.0),
    ]}}}
    result = compute_contact_pitches(payload, 542881)
    assert len(result.pitches) == 1
    card = result.pitches[0]
    assert card.reasons == ["home_run", "high_ev_contact"]
    assert card.exit_velocity_mph == 108.6
    assert card.launch_angle_deg == 28.0
    assert card.outcome == "Home Run"


def test_home_run_without_hit_data_card_present_ev_and_la_none():
    payload = {"liveData": {"plays": {"allPlays": [
        _play(result="Home Run", include_hit_data=False),
    ]}}}
    result = compute_contact_pitches(payload, 542881)
    assert len(result.pitches) == 1
    card = result.pitches[0]
    assert card.reasons == ["home_run"]
    assert card.exit_velocity_mph is None
    assert card.launch_angle_deg is None


def test_exit_velocity_exactly_threshold_is_included():
    payload = {"liveData": {"plays": {"allPlays": [
        _play(result="Flyout", exit_velocity=100.0),
    ]}}}
    result = compute_contact_pitches(payload, 542881)
    assert len(result.pitches) == 1
    assert result.pitches[0].reasons == ["high_ev_contact"]


def test_exit_velocity_just_below_threshold_excluded():
    payload = {"liveData": {"plays": {"allPlays": [
        _play(result="Flyout", exit_velocity=99.9),
    ]}}}
    result = compute_contact_pitches(payload, 542881)
    assert result.pitches == []


@pytest.mark.parametrize("bad_ev", ["", float("nan"), 0])
def test_exit_velocity_missing_or_invalid_treated_as_missing(bad_ev):
    payload = {"liveData": {"plays": {"allPlays": [
        _play(result="Flyout", exit_velocity=bad_ev),
    ]}}}
    result = compute_contact_pitches(payload, 542881)
    assert result.pitches == []


def test_other_pitcher_excluded():
    payload = {"liveData": {"plays": {"allPlays": [
        _play(pitcher_id=701002, result="Home Run", exit_velocity=115.0),
    ]}}}
    result = compute_contact_pitches(payload, 542881)
    assert result.pitches == []


def test_incomplete_play_excluded():
    payload = {"liveData": {"plays": {"allPlays": [
        _play(result="Home Run", exit_velocity=115.0, complete=False),
    ]}}}
    result = compute_contact_pitches(payload, 542881)
    assert result.pitches == []


def test_missing_coordinates_region_none_card_present():
    payload = {"liveData": {"plays": {"allPlays": [
        _play(result="Home Run", exit_velocity=105.0, plate_x=None, plate_z=None),
    ]}}}
    result = compute_contact_pitches(payload, 542881)
    assert len(result.pitches) == 1
    card = result.pitches[0]
    assert card.region is None
    assert card.plate_x is None
    assert card.plate_z is None


def test_missing_bat_side_is_none():
    payload = {"liveData": {"plays": {"allPlays": [
        _play(result="Home Run", exit_velocity=105.0, bat_side=None),
    ]}}}
    result = compute_contact_pitches(payload, 542881)
    assert result.pitches[0].batter_side is None


def test_order_by_at_bat_index():
    payload = {"liveData": {"plays": {"allPlays": [
        _play(at_bat_index=3, result="Home Run", exit_velocity=110.0),
        _play(at_bat_index=1, result="Flyout", exit_velocity=101.0),
    ]}}}
    result = compute_contact_pitches(payload, 542881)
    assert [card.at_bat_index for card in result.pitches] == [1, 3]


def test_high_ev_threshold_field_matches_engine_constant():
    from app.rules.engine import HARD_CONTACT_EXIT_VELOCITY_MPH

    result = compute_contact_pitches({"liveData": {"plays": {"allPlays": []}}}, 542881)
    assert result.high_ev_threshold_mph == HARD_CONTACT_EXIT_VELOCITY_MPH


def test_card_counts_match_outcome_context_on_shared_payload():
    payload = {"liveData": {"plays": {"allPlays": [
        _play(at_bat_index=0, result="Home Run", exit_velocity=108.6),
        _play(at_bat_index=1, result="Double", exit_velocity=95.0),
        _play(at_bat_index=2, result="Single", exit_velocity=None, include_hit_data=False),
        _play(at_bat_index=3, result="Flyout", exit_velocity=101.9),
        _play(at_bat_index=4, result="Home Run", exit_velocity=120.0, complete=False),
        _play(at_bat_index=5, result="Home Run", exit_velocity=115.0, pitcher_id=701002),
    ]}}}

    contact = compute_contact_pitches(payload, 542881)
    outcome = compute_pitcher_outcome_context(payload, 542881)

    high_ev_cards = [card for card in contact.pitches if "high_ev_contact" in card.reasons]
    home_run_cards = [card for card in contact.pitches if "home_run" in card.reasons]
    assert len(high_ev_cards) == outcome.hard_hit_contacts
    assert len(home_run_cards) == outcome.home_runs_allowed


def test_contact_pitches_route_is_independent_of_statcast(client, monkeypatch):
    payload = {"liveData": {"plays": {"allPlays": [
        _play(pitcher_id=123, result="Home Run", exit_velocity=110.0),
    ]}}}
    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(payload))
    response = client.get("/api/live/games/777/pitchers/123/contact-pitches")
    assert response.status_code == 200
    body = response.json()
    assert len(body["pitches"]) == 1
    assert body["pitches"][0]["reasons"] == ["home_run", "high_ev_contact"]
    empty = client.get("/api/live/games/777/pitchers/9999/contact-pitches")
    assert empty.json()["pitches"] == []


def test_contact_pitches_route_preserves_live_source_errors(client, monkeypatch):
    for error, expected in [(LiveGameNotFound("missing"), 404),
                            (LiveFeedError("feed down"), 502)]:
        monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(error=error))
        assert client.get(
            "/api/live/games/777/pitchers/123/contact-pitches"
        ).status_code == expected
