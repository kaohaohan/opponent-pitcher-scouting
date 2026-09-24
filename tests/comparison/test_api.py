"""GET /api/live/games/{game_id}/pitchers/{pitcher_id}/comparison, wired
to a stub live feed and a fake Statcast source. No live MLB or Baseball
Savant calls."""

from __future__ import annotations

import json
from collections.abc import Iterator
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.comparison import api as comparison_api
from app.comparison.schemas import ComparisonNote, PregameLiveComparison
from app.main import create_app
from app.pregame.api import get_pitch_source
from app.pregame.schemas import PitchRecord
from app.sources.live import LiveGameNotFound, LiveSourceError
from tests.comparison.fakes import (
    CountingFakePitchDataSource,
    FakeComparisonNoteProvider,
    StubLiveSource,
)
from tests.pregame.fakes import FakePitchDataSource

LIVE_FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "mlb_live_feed_776743_20250814_230000.json"
)
LIVE_PAYLOAD = json.loads(LIVE_FIXTURE.read_text(encoding="utf-8"))
PITCHER_ID = 542881  # Tyler Anderson: one Four-Seam (91.2mph), one Slider (87.5mph)


def statcast_record(pitch_type: str, count: int, release_speed: float) -> list[PitchRecord]:
    return [
        PitchRecord(
            pitcher_id=PITCHER_ID,
            game_pk=700001,
            game_date=date(2025, 8, 1),
            at_bat_number=i + 1,
            pitch_number=1,
            pitch_type=pitch_type,
            balls=0,
            strikes=0,
            release_speed=release_speed,
        )
        for i in range(count)
    ]


@pytest.fixture()
def client(monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setattr(main, "create_all", lambda: None)
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _override_pitch_source(app, records: list[PitchRecord]) -> None:
    app.dependency_overrides[get_pitch_source] = lambda: FakePitchDataSource(records)


def test_comparison_happy_path_with_baseline_and_live_data(client, monkeypatch):
    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(LIVE_PAYLOAD))
    records = statcast_record("SL", 32, 85.6) + statcast_record("FF", 44, 95.1)
    _override_pitch_source(client.app, records)

    response = client.get(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison",
        params={"start_date": "2025-08-01", "end_date": "2025-08-15"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["baseline_available"] is True
    assert body["live_available"] is True
    assert body["pitcher_name"] == "Tyler Anderson"
    by_type = {row["pitch_type"]: row for row in body["rows"]}
    assert by_type["SL"]["baseline_usage_pct"] == pytest.approx(32 / 76 * 100, abs=0.1)
    assert by_type["SL"]["live_usage_pct"] == 50.0


def test_comparison_no_baseline_returns_live_only(client, monkeypatch):
    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(LIVE_PAYLOAD))
    _override_pitch_source(client.app, [])

    response = client.get(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison",
        params={"start_date": "2025-08-01", "end_date": "2025-08-15"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["baseline_available"] is False
    assert body["live_available"] is True
    assert any("No pregame Statcast baseline" in note for note in body["limitations"])


def test_comparison_no_live_sample_returns_baseline_only(client, monkeypatch):
    empty_payload = {
        "gameData": {
            "teams": {"away": {"id": 1, "name": "Away"}, "home": {"id": 2, "name": "Home"}}
        },
        "liveData": {"plays": {"allPlays": []}},
    }
    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(empty_payload))
    _override_pitch_source(client.app, statcast_record("SL", 25, 85.6))

    response = client.get(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison",
        params={"start_date": "2025-08-01", "end_date": "2025-08-15"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["live_available"] is False
    assert body["overall_live_status"] == "insufficient_sample"
    assert any("not thrown a tracked pitch" in note for note in body["limitations"])


def test_comparison_game_not_found_returns_404(client, monkeypatch):
    monkeypatch.setattr(
        comparison_api,
        "LiveSource",
        StubLiveSource(error=LiveGameNotFound("no such game")),
    )
    _override_pitch_source(client.app, [])

    response = client.get(
        f"/api/live/games/999999/pitchers/{PITCHER_ID}/comparison",
        params={"start_date": "2025-08-01", "end_date": "2025-08-15"},
    )

    assert response.status_code == 404


def test_comparison_mlb_feed_down_returns_502(client, monkeypatch):
    monkeypatch.setattr(
        comparison_api,
        "LiveSource",
        StubLiveSource(error=LiveSourceError("upstream is down")),
    )
    _override_pitch_source(client.app, [])

    response = client.get(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison",
        params={"start_date": "2025-08-01", "end_date": "2025-08-15"},
    )

    assert response.status_code == 502


def test_comparison_statcast_down_returns_502(client, monkeypatch):
    from app.pregame.sources.statcast import StatcastFetchError

    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(LIVE_PAYLOAD))

    class FailingSource(FakePitchDataSource):
        def fetch_pitcher_pitches(self, pitcher_id, start_date, end_date):
            raise StatcastFetchError("Baseball Savant is down")

    client.app.dependency_overrides[get_pitch_source] = lambda: FailingSource()

    response = client.get(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison",
        params={"start_date": "2025-08-01", "end_date": "2025-08-15"},
    )

    assert response.status_code == 502


def test_comparison_unsupported_pitcher_has_no_baseline_or_live_data(client, monkeypatch):
    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(LIVE_PAYLOAD))
    _override_pitch_source(client.app, [])

    response = client.get(
        "/api/live/games/776743/pitchers/999999/comparison",
        params={"start_date": "2025-08-01", "end_date": "2025-08-15"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["baseline_available"] is False
    assert body["live_available"] is False
    assert body["rows"] == []


def test_note_endpoint_returns_the_generated_note(client, monkeypatch):
    from app.comparison.api import get_comparison_note_provider

    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(LIVE_PAYLOAD))
    _override_pitch_source(client.app, statcast_record("SL", 25, 85.6))
    fake_note = FakeComparisonNoteProvider(
        ComparisonNote(summary="Notable slider usage.", notable_changes=[], sample_note="ok")
    )
    client.app.dependency_overrides[get_comparison_note_provider] = lambda: fake_note

    response = client.post(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison/note",
        params={"start_date": "2025-08-01", "end_date": "2025-08-15"},
    )

    assert response.status_code == 200
    assert response.json()["summary"] == "Notable slider usage."
    assert len(fake_note.received_comparisons) == 1
    assert isinstance(fake_note.received_comparisons[0], PregameLiveComparison)
    assert fake_note.received_comparisons[0].outcome_context.home_runs_allowed == 1
    assert fake_note.received_comparisons[0].outcome_context.hard_hit_contacts == 1
    assert fake_note.received_comparisons[0].outcome_context.max_exit_velocity_mph == 104.3


def test_note_endpoint_caches_repeated_requests_for_the_same_comparison_state(client, monkeypatch):
    """Repeated clicks for an unchanged live state must spend Gemini quota once."""
    from app.comparison.api import get_comparison_note_provider

    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(LIVE_PAYLOAD))
    _override_pitch_source(client.app, statcast_record("SL", 25, 85.6))
    fake_note = FakeComparisonNoteProvider(
        ComparisonNote(summary="Cached note.", notable_changes=[], sample_note="ok")
    )
    client.app.dependency_overrides[get_comparison_note_provider] = lambda: fake_note
    params = {"start_date": "2025-08-01", "end_date": "2025-08-15"}

    first = client.post(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison/note", params=params
    )
    second = client.post(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison/note", params=params
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert len(fake_note.received_comparisons) == 1


def test_note_cache_invalidates_when_outcomes_change_but_pitch_comparison_does_not(
    client, monkeypatch
):
    from app.comparison.api import get_comparison_note_provider

    payload = deepcopy(LIVE_PAYLOAD)
    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(payload))
    _override_pitch_source(client.app, statcast_record("SL", 25, 85.6))
    fake_note = FakeComparisonNoteProvider(
        ComparisonNote(summary="Outcome note.", notable_changes=[], sample_note="ok")
    )
    client.app.dependency_overrides[get_comparison_note_provider] = lambda: fake_note
    params = {"start_date": "2025-08-01", "end_date": "2025-08-15"}
    endpoint = f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison/note"

    first = client.post(endpoint, params=params)
    first_input = fake_note.received_comparisons[0]
    payload["liveData"]["plays"]["allPlays"].append(
        {
            "about": {"atBatIndex": 99, "isComplete": True},
            "matchup": {"pitcher": {"id": PITCHER_ID}},
            "result": {"event": "Home Run"},
            "playEvents": [],
        }
    )
    second = client.post(endpoint, params=params)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first_input.live_total_pitches == fake_note.received_comparisons[1].live_total_pitches
    assert first_input.outcome_context.home_runs_allowed == 1
    assert fake_note.received_comparisons[1].outcome_context.home_runs_allowed == 2
    assert len(fake_note.received_comparisons) == 2


def test_note_endpoint_returns_503_when_gemini_is_unconfigured(client, monkeypatch):
    from app.comparison.api import get_comparison_note_provider
    from app.comparison.llm.gemini import GeminiConfigurationError

    class UnconfiguredProvider:
        def generate_note(self, comparison):
            raise GeminiConfigurationError("GEMINI_API_KEY is not set")

    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(LIVE_PAYLOAD))
    _override_pitch_source(client.app, statcast_record("SL", 25, 85.6))
    client.app.dependency_overrides[get_comparison_note_provider] = UnconfiguredProvider

    response = client.post(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison/note",
        params={"start_date": "2025-08-01", "end_date": "2025-08-15"},
    )

    assert response.status_code == 503


def test_note_endpoint_returns_502_on_malformed_gemini_response(client, monkeypatch):
    from app.comparison.api import get_comparison_note_provider
    from app.comparison.llm.gemini import GeminiMalformedResponseError

    class MalformedProvider:
        def generate_note(self, comparison):
            raise GeminiMalformedResponseError("did not match schema")

    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(LIVE_PAYLOAD))
    _override_pitch_source(client.app, statcast_record("SL", 25, 85.6))
    client.app.dependency_overrides[get_comparison_note_provider] = MalformedProvider

    response = client.post(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison/note",
        params={"start_date": "2025-08-01", "end_date": "2025-08-15"},
    )

    assert response.status_code == 502


def test_baseline_cache_prevents_a_second_statcast_fetch_within_ttl(client, monkeypatch):
    """Two polls of the same pitcher/window should hit the fake Statcast
    source once, not twice — `app.comparison.api`'s baseline cache should
    serve the second request from memory."""
    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(LIVE_PAYLOAD))
    counting_source = CountingFakePitchDataSource(statcast_record("SL", 25, 85.6))
    client.app.dependency_overrides[get_pitch_source] = lambda: counting_source

    params = {"start_date": "2025-08-01", "end_date": "2025-08-15"}
    first = client.get(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison", params=params
    )
    second = client.get(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison", params=params
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert counting_source.call_count == 1


def test_baseline_cache_is_keyed_by_pitcher_and_window(client, monkeypatch):
    """A different date window is a cache miss, not a stale hit."""
    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(LIVE_PAYLOAD))
    counting_source = CountingFakePitchDataSource(statcast_record("SL", 25, 85.6))
    client.app.dependency_overrides[get_pitch_source] = lambda: counting_source

    client.get(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison",
        params={"start_date": "2025-08-01", "end_date": "2025-08-15"},
    )
    client.get(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison",
        params={"start_date": "2025-07-01", "end_date": "2025-07-15"},
    )

    assert counting_source.call_count == 2


def test_get_comparison_never_calls_the_llm_fake(client, monkeypatch):
    """The numeric comparison route must stay safe to poll — it should
    never touch the note provider, even indirectly."""
    from app.comparison.api import get_comparison_note_provider

    class ExplodingProvider:
        def generate_note(self, comparison):
            raise AssertionError("GET comparison must never call the note provider")

    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(LIVE_PAYLOAD))
    _override_pitch_source(client.app, statcast_record("SL", 25, 85.6))
    client.app.dependency_overrides[get_comparison_note_provider] = ExplodingProvider

    response = client.get(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison",
        params={"start_date": "2025-08-01", "end_date": "2025-08-15"},
    )

    assert response.status_code == 200


def test_note_failure_never_affects_the_comparison_get_endpoint(client, monkeypatch):
    """Failure isolation, end to end: the note endpoint fails, but the
    comparison GET endpoint — a separate request, computed independently
    — still returns the full numeric table."""
    from app.comparison.api import get_comparison_note_provider
    from app.comparison.llm.gemini import GeminiRequestError

    class FailingProvider:
        def generate_note(self, comparison):
            raise GeminiRequestError("Gemini request failed: timed out")

    monkeypatch.setattr(comparison_api, "LiveSource", StubLiveSource(LIVE_PAYLOAD))
    _override_pitch_source(client.app, statcast_record("SL", 25, 85.6))
    client.app.dependency_overrides[get_comparison_note_provider] = FailingProvider

    note_response = client.post(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison/note",
        params={"start_date": "2025-08-01", "end_date": "2025-08-15"},
    )
    comparison_response = client.get(
        f"/api/live/games/776743/pitchers/{PITCHER_ID}/comparison",
        params={"start_date": "2025-08-01", "end_date": "2025-08-15"},
    )

    assert note_response.status_code == 502
    assert comparison_response.status_code == 200
    assert comparison_response.json()["baseline_available"] is True
    assert comparison_response.json()["rows"]
