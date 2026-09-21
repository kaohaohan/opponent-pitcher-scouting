"""The LLM boundary: providers receive a structured PregameContext and
nothing else, and Gemini credentials fail clearly rather than silently.

No live Gemini calls here — FakeLLMProvider stands in for GeminiProvider.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from app.config import settings
from app.pregame.context import PregameContextBuilder
from app.pregame.llm.gemini import GeminiConfigurationError, GeminiProvider
from app.pregame.schemas import PregameContext
from tests.pregame.fakes import FakeLLMProvider


@pytest.fixture()
def context() -> PregameContext:
    return PregameContextBuilder().build(
        pitcher_id=1, start_date=date(2025, 8, 1), end_date=date(2025, 8, 2), records=[]
    )


def test_fake_provider_receives_the_structured_context_object(context):
    provider = FakeLLMProvider(brief="Sample brief text")

    brief = provider.generate_brief(context)

    assert brief == "Sample brief text"
    assert provider.received_contexts == [context]
    assert isinstance(provider.received_contexts[0], PregameContext)


def test_gemini_provider_fails_clearly_when_api_key_is_missing(context, monkeypatch):
    # Settings is a frozen dataclass; replace the module-level instance that
    # GeminiProvider reads from, rather than mutating it in place.
    monkeypatch.setattr(
        "app.pregame.llm.gemini.settings",
        dataclasses.replace(settings, gemini_api_key=None),
    )
    provider = GeminiProvider()

    with pytest.raises(GeminiConfigurationError, match="GEMINI_API_KEY"):
        provider.generate_brief(context)
