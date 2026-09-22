"""The comparison-note LLM boundary: providers receive a structured
PregameLiveComparison and nothing else; Gemini credential, request, and
malformed-response failures each fail clearly and distinctly.

No live Gemini calls here — FakeGenAIClient stands in for genai.Client.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from app.comparison.compare import build_comparison
from app.comparison.live_metrics import LivePitcherMetrics, LivePitchTypeMetric
from app.comparison.llm import gemini as gemini_module
from app.comparison.llm.gemini import (
    GeminiComparisonProvider,
    GeminiConfigurationError,
    GeminiMalformedResponseError,
    GeminiRequestError,
)
from app.comparison.schemas import ComparisonNote, PregameLiveComparison
from app.config import settings
from tests.comparison.fakes import FakeComparisonNoteProvider, FakeGenAIClient


@pytest.fixture()
def comparison() -> PregameLiveComparison:
    live = LivePitcherMetrics(
        pitcher_id=542881,
        pitcher_name="Tyler Anderson",
        total_pitches=1,
        by_type=[
            LivePitchTypeMetric(pitch_type="Slider", count=1, percentage=100.0, avg_velocity=87.5)
        ],
    )
    return build_comparison(
        game_id="776743",
        pitcher_id=542881,
        baseline_start_date=date(2025, 8, 1),
        baseline_end_date=date(2025, 8, 15),
        baseline=None,
        live=live,
    )


def test_fake_provider_receives_the_structured_comparison_object(comparison):
    provider = FakeComparisonNoteProvider()

    note = provider.generate_note(comparison)

    assert note.summary == "fake summary"
    assert provider.received_comparisons == [comparison]
    assert isinstance(provider.received_comparisons[0], PregameLiveComparison)


def test_gemini_provider_fails_clearly_when_api_key_is_missing(comparison, monkeypatch):
    monkeypatch.setattr(
        gemini_module, "settings", dataclasses.replace(settings, gemini_api_key=None)
    )
    provider = GeminiComparisonProvider()

    with pytest.raises(GeminiConfigurationError, match="GEMINI_API_KEY"):
        provider.generate_note(comparison)


def test_gemini_provider_wraps_request_failures(comparison, monkeypatch):
    monkeypatch.setattr(
        gemini_module, "settings", dataclasses.replace(settings, gemini_api_key="test-key")
    )
    fake_client = FakeGenAIClient(error=TimeoutError("upstream timed out"))
    monkeypatch.setattr(gemini_module.genai, "Client", lambda **_kwargs: fake_client)
    provider = GeminiComparisonProvider()

    with pytest.raises(GeminiRequestError, match="upstream timed out"):
        provider.generate_note(comparison)


def test_gemini_provider_rejects_malformed_json_response(comparison, monkeypatch):
    monkeypatch.setattr(
        gemini_module, "settings", dataclasses.replace(settings, gemini_api_key="test-key")
    )
    fake_client = FakeGenAIClient(response_text="not valid json at all")
    monkeypatch.setattr(gemini_module.genai, "Client", lambda **_kwargs: fake_client)
    provider = GeminiComparisonProvider()

    with pytest.raises(GeminiMalformedResponseError):
        provider.generate_note(comparison)


def test_gemini_provider_rejects_response_missing_required_fields(comparison, monkeypatch):
    monkeypatch.setattr(
        gemini_module, "settings", dataclasses.replace(settings, gemini_api_key="test-key")
    )
    fake_client = FakeGenAIClient(response_text='{"summary": "only a summary"}')
    monkeypatch.setattr(gemini_module.genai, "Client", lambda **_kwargs: fake_client)
    provider = GeminiComparisonProvider()

    with pytest.raises(GeminiMalformedResponseError):
        provider.generate_note(comparison)


def test_gemini_provider_parses_a_well_formed_structured_response(comparison, monkeypatch):
    monkeypatch.setattr(
        gemini_module, "settings", dataclasses.replace(settings, gemini_api_key="test-key")
    )
    payload = (
        '{"summary": "Leaning heavily on the slider tonight.", '
        '"notable_changes": [{"metric": "slider_usage", "description": "Up sharply."}], '
        '"sample_note": "Small live sample so far."}'
    )
    fake_client = FakeGenAIClient(response_text=payload)
    monkeypatch.setattr(gemini_module.genai, "Client", lambda **_kwargs: fake_client)
    provider = GeminiComparisonProvider()

    note = provider.generate_note(comparison)

    assert isinstance(note, ComparisonNote)
    assert note.summary == "Leaning heavily on the slider tonight."
    assert note.notable_changes[0].metric == "slider_usage"
    assert note.sample_note == "Small live sample so far."
