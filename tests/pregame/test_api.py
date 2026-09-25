"""POST /api/pregame/brief, wired to fake source and LLM boundaries.

No live Statcast or Gemini calls: fetch and generation are swapped for
fakes via FastAPI dependency overrides, the same seam GeminiProvider is
injected through in production.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import create_app
from app.pregame.api import get_llm_provider, get_pitch_source
from app.pregame.schemas import PitchRecord
from tests.pregame.fakes import FakeLLMProvider, FakePitchDataSource


def make_record(pitch_type: str, balls: int = 0, strikes: int = 0, **overrides) -> PitchRecord:
    defaults = dict(
        pitcher_id=600001,
        game_pk=700001,
        game_date=date(2025, 8, 10),
        at_bat_number=1,
        pitch_number=1,
        pitch_type=pitch_type,
        balls=balls,
        strikes=strikes,
        release_speed=95.0,
    )
    defaults.update(overrides)
    return PitchRecord(**defaults)


@pytest.fixture()
def fake_llm() -> FakeLLMProvider:
    return FakeLLMProvider(brief="Sample pre-game brief.")


@pytest.fixture()
def client(monkeypatch, fake_llm) -> Iterator[TestClient]:
    # Phase 1's startup hook would otherwise touch the real database; Phase 2
    # makes no database calls at all, but create_all() still runs on startup.
    monkeypatch.setattr(main, "create_all", lambda: None)

    app = create_app()
    records = [make_record("FF") for _ in range(25)] + [make_record("SL") for _ in range(3)]
    app.dependency_overrides[get_pitch_source] = lambda: FakePitchDataSource(records)
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_brief_endpoint_returns_context_and_brief_text(client, fake_llm):
    response = client.post(
        "/api/pregame/brief",
        json={
            "pitcher_id": 600001,
            "start_date": "2025-08-01",
            "end_date": "2025-08-15",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["brief"] == "Sample pre-game brief."
    assert body["context"]["pitcher_id"] == 600001
    assert body["context"]["total_pitches"] == 28


def test_llm_provider_receives_the_backend_computed_context(client, fake_llm):
    client.post(
        "/api/pregame/brief",
        json={
            "pitcher_id": 600001,
            "start_date": "2025-08-01",
            "end_date": "2025-08-15",
        },
    )

    assert len(fake_llm.received_contexts) == 1
    context = fake_llm.received_contexts[0]
    by_type = {row.pitch_type: row for row in context.pitch_usage_by_type}
    assert by_type["FF"].count == 25
    assert by_type["SL"].status.value == "insufficient_sample"


def test_brief_endpoint_reports_a_statcast_failure_as_a_clear_error(client):
    from app.pregame.sources.statcast import StatcastFetchError

    def broken_source():
        class BrokenSource:
            name = "broken"

            def fetch_pitcher_pitches(self, *args, **kwargs):
                raise StatcastFetchError("upstream is down")

        return BrokenSource()

    client.app.dependency_overrides[get_pitch_source] = broken_source
    response = client.post(
        "/api/pregame/brief",
        json={"pitcher_id": 1, "start_date": "2025-08-01", "end_date": "2025-08-02"},
    )

    assert response.status_code == 502
    assert "upstream is down" in response.json()["detail"]


def test_brief_endpoint_reports_missing_credentials_as_a_clear_error(client):
    from app.pregame.llm.gemini import GeminiConfigurationError

    def unconfigured_llm():
        class UnconfiguredProvider:
            def generate_brief(self, context):
                raise GeminiConfigurationError("GEMINI_API_KEY is not set")

        return UnconfiguredProvider()

    client.app.dependency_overrides[get_llm_provider] = unconfigured_llm
    response = client.post(
        "/api/pregame/brief",
        json={"pitcher_id": 1, "start_date": "2025-08-01", "end_date": "2025-08-02"},
    )

    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_brief_endpoint_returns_502_when_brief_contains_a_banned_phrase(client):
    """The public feed records where a pitch finished, not intent — a brief
    that describes execution ("missed his spot") is rejected, not served."""

    class BannedPhraseProvider:
        def generate_brief(self, context):
            return "He has missed his spot with the fastball lately."

    client.app.dependency_overrides[get_llm_provider] = lambda: BannedPhraseProvider()

    response = client.post(
        "/api/pregame/brief",
        json={"pitcher_id": 600001, "start_date": "2025-08-01", "end_date": "2025-08-15"},
    )

    assert response.status_code == 502
    assert "missed his spot" in response.json()["detail"].lower()


def test_phase1_router_still_answers_alongside_the_pregame_router(client):
    # A DB-free Phase 1 route is enough to prove both routers coexist; the
    # DB-backed Phase 1 endpoints are exercised in tests/test_api.py under
    # their own isolated database fixture.
    assert client.get("/health").json() == {"status": "ok"}
