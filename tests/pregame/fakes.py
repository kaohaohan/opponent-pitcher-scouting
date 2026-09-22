"""Test doubles for the Phase 2 boundaries. No live Statcast or Gemini calls
in tests."""

from __future__ import annotations

from datetime import date

from app.pregame.llm.base import LLMProvider
from app.pregame.schemas import PitcherSearchResult, PitchRecord, PregameContext
from app.pregame.sources.base import PitchDataSource


class FakePitchDataSource(PitchDataSource):
    """Returns canned records instead of calling Baseball Savant."""

    name = "fake"

    def __init__(self, records: list[PitchRecord] | None = None) -> None:
        self.records = records or []

    def fetch_pitcher_pitches(
        self, pitcher_id: int, start_date: date, end_date: date
    ) -> list[PitchRecord]:
        return self.records


class FakeLLMProvider(LLMProvider):
    """Records the context it was given and returns canned text.

    Lets tests assert that a provider receives a structured `PregameContext`
    object — never a raw prompt string, a database session, or anything it
    could use to compute its own statistics.
    """

    def __init__(self, brief: str = "fake brief") -> None:
        self.brief = brief
        self.received_contexts: list[PregameContext] = []

    def generate_brief(self, context: PregameContext) -> str:
        self.received_contexts.append(context)
        return self.brief


class FakePitcherSearchSource:
    """Returns canned pitcher matches instead of calling MLB's people search."""

    name = "fake"

    def __init__(self, results: list[PitcherSearchResult] | None = None) -> None:
        self.results = results or []
        self.received_queries: list[str] = []

    def search(self, query: str) -> list[PitcherSearchResult]:
        self.received_queries.append(query)
        return self.results
