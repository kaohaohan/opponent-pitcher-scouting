"""Deterministic MLB adapter and pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.sources import LiveSource

LIVE_FIXTURE = (
    Path(__file__).parent / "fixtures" / "mlb_live_feed_776743_20250814_230000.json"
)


def _source(fixture_path=LIVE_FIXTURE):
    payload = fixture_path.read_text(encoding="utf-8")
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=json.loads(payload))
        )
    )
    return LiveSource(776743, ("657557",), client=client)


def test_live_source_maps_completed_watched_plays_and_selects_terminal_pitch():
    source = _source()

    events = list(source.events())

    assert [event["at_bat_index"] for event in events] == [4, 7, 8]
    assert events[0] == {
        "game_id": "776743",
        "external_player_id": "657557",
        "player_name": "Paul DeJong",
        "team": "Chicago White Sox",
        "at_bat_index": 4,
        "inning": 2,
        "result": "Home Run",
        "pitcher": "Tyler Anderson",
        "is_complete": True,
        "pitch_type": "Slider",
        "pitch_velocity": 87.5,
        "exit_velocity": 104.3,
        "launch_angle": 27.0,
    }
    assert events[1]["pitch_velocity"] is None
    assert events[2]["player_name"] is None


def test_live_source_is_finite_and_processor_reuses_existing_rules(processor):
    report = processor.process_source(_source())

    assert report.source == "live"
    assert report.events_read == 3
    assert report.stored == 2
    assert report.invalid == 1
    assert report.alerts_created == 2

    second = processor.process_source(_source())
    assert second.stored == 0
    assert second.duplicates == 2
    assert second.invalid == 1
    assert second.alerts_created == 0


def test_live_source_rejects_bad_top_level_schema():
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"gameData": {}}))
    )
    source = LiveSource(776743, ("657557",), client=client)

    try:
        list(source.events())
    except Exception as exc:
        assert "liveData" in str(exc)
    else:  # pragma: no cover - assertion makes the failure explicit
        raise AssertionError("invalid feed schema was accepted")
