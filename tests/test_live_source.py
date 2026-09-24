"""Deterministic MLB adapter and pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

import app.sources._swr_cache as swr_cache_module
import app.sources.live as live_module
from app.sources import LiveGameNotFound, LiveSource
from app.sources._swr_cache import synchronous_executor

LIVE_FIXTURE = (
    Path(__file__).parent / "fixtures" / "mlb_live_feed_776743_20250814_230000.json"
)


def _source(fixture_path=LIVE_FIXTURE, batter_ids=("657557",), pitcher_ids=()):
    payload = fixture_path.read_text(encoding="utf-8")
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=json.loads(payload))
        )
    )
    return LiveSource(776743, batter_ids=batter_ids, pitcher_ids=pitcher_ids, client=client)


def _counting_client(status_code: int = 200, fixture_path: Path = LIVE_FIXTURE):
    """A client that records one call per request and serves canned responses."""
    calls: list[None] = []
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(None)
        if status_code == 404:
            return httpx.Response(404)
        return httpx.Response(status_code, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_live_source_maps_completed_watched_plays_and_selects_terminal_pitch():
    source = _source()

    events = list(source.events())

    assert [event["at_bat_index"] for event in events] == [4, 7, 8]
    assert events[0] == {
        "game_id": "776743",
        "batter_id": "657557",
        "batter_name": "Paul DeJong",
        "batter_team": "Chicago White Sox",
        "pitcher_id": "542881",
        "pitcher_name": "Tyler Anderson",
        "pitcher_team": "Los Angeles Angels",
        "matched_roles": ("batter",),
        "at_bat_index": 4,
        "inning": 2,
        "result": "Home Run",
        "is_complete": True,
        "pitch_type": "Slider",
        "pitch_velocity": 87.5,
        "exit_velocity": 104.3,
        "launch_angle": 27.0,
    }
    assert events[1]["pitch_velocity"] is None
    assert events[2]["batter_name"] is None


def test_live_source_can_watch_pitchers_without_batters():
    events = list(_source(batter_ids=(), pitcher_ids=("701002",)).events())

    assert [event["at_bat_index"] for event in events] == [6, 7]
    assert {event["matched_roles"] for event in events} == {("pitcher",)}
    assert events[0]["batter_name"] == "Unrelated Batter"
    assert events[0]["pitcher_name"] == "Two-Way Reserve"


def test_live_source_emits_once_when_batter_and_pitcher_both_match():
    events = list(_source(batter_ids=("657557",), pitcher_ids=("542881",)).events())

    assert [event["at_bat_index"] for event in events] == [4, 7, 8]
    assert events[0]["matched_roles"] == ("batter", "pitcher")


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


def test_live_source_discovers_participants_from_boxscore_and_observed_plays():
    participants = _source().discover_participants()

    assert participants.game_id == "776743"
    assert participants.teams["away"].name == "Chicago White Sox"
    by_id = {participant.player_id: participant for participant in participants.participants}
    assert by_id[657557].roles == ["batter"]
    assert by_id[542881].roles == ["pitcher"]
    assert by_id[701002].roles == ["batter", "pitcher"]


def test_live_source_fetch_snapshot_returns_the_raw_feed_payload():
    payload = _source().fetch_snapshot()

    assert payload["gameData"]["teams"]["away"]["name"] == "Chicago White Sox"
    assert isinstance(payload["liveData"]["plays"]["allPlays"], list)


def test_live_snapshot_cache_reuses_payload_within_ttl():
    client, calls = _counting_client()
    other_client, other_calls = _counting_client()

    first = LiveSource(999001, client=client).fetch_snapshot()
    second = LiveSource(999001, client=other_client).fetch_snapshot()

    assert first == second
    assert len(calls) == 1
    assert len(other_calls) == 0  # cache hit never touches the second client


def test_live_snapshot_cache_serves_stale_and_refreshes_in_background_after_ttl(monkeypatch):
    # Stale-while-revalidate: once the fresh TTL elapses but before max_stale,
    # a call gets the old payload back immediately *and* triggers exactly one
    # background refresh. A synchronous executor makes that refresh happen
    # inline, so the test can observe it deterministically.
    fake_now = [1_000.0]
    monkeypatch.setattr(swr_cache_module.time, "monotonic", lambda: fake_now[0])
    monkeypatch.setattr(live_module._snapshot_cache, "_executor", synchronous_executor())

    client, calls = _counting_client()
    first = LiveSource(999002, client=client).fetch_snapshot()
    assert len(calls) == 1

    fake_now[0] += live_module.LIVE_SNAPSHOT_TTL_SECONDS + 0.01
    second_client, second_calls = _counting_client()
    second = LiveSource(999002, client=second_client).fetch_snapshot()
    # Served from the stale cache, not the calling instance's own client...
    assert second == first
    assert len(calls) == 1
    # ...but that call's background refresh (run inline here) hit upstream
    # once, through the calling instance's own loader.
    assert len(second_calls) == 1

    # A subsequent call within the new fresh window reuses the refreshed
    # value without touching MLB again.
    third_client, third_calls = _counting_client()
    LiveSource(999002, client=third_client).fetch_snapshot()
    assert len(third_calls) == 0


def test_live_snapshot_cache_loads_synchronously_once_past_max_stale(monkeypatch):
    fake_now = [2_000.0]
    monkeypatch.setattr(swr_cache_module.time, "monotonic", lambda: fake_now[0])

    client, calls = _counting_client()
    LiveSource(999006, client=client).fetch_snapshot()
    assert len(calls) == 1

    fake_now[0] += live_module.LIVE_SNAPSHOT_MAX_STALE_SECONDS + 0.01
    second_client, second_calls = _counting_client()
    LiveSource(999006, client=second_client).fetch_snapshot()
    # Too stale to serve: the caller blocks on its own upstream call.
    assert len(calls) == 1
    assert len(second_calls) == 1


def test_live_snapshot_cache_does_not_cache_errors():
    client, calls = _counting_client(status_code=404)
    source = LiveSource(999003, client=client)

    for _ in range(2):
        try:
            source.fetch_snapshot()
        except LiveGameNotFound:
            pass
        else:  # pragma: no cover - assertion makes the failure explicit
            raise AssertionError("expected LiveGameNotFound")

    assert len(calls) == 2  # neither failed attempt was cached


def test_live_snapshot_cache_is_independent_per_game_id():
    client_a, calls_a = _counting_client()
    client_b, calls_b = _counting_client()

    LiveSource(999004, client=client_a).fetch_snapshot()
    LiveSource(999005, client=client_b).fetch_snapshot()
    LiveSource(999004, client=client_a).fetch_snapshot()
    LiveSource(999005, client=client_b).fetch_snapshot()

    assert len(calls_a) == 1
    assert len(calls_b) == 1
