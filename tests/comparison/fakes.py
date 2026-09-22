"""Test doubles for the Phase 5 boundaries. No live MLB, Statcast, or
Gemini calls in tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.comparison.llm.base import ComparisonNoteProvider
from app.comparison.schemas import ComparisonNote, PregameLiveComparison


class StubLiveSource:
    """Stands in for `app.sources.live.LiveSource` in comparison API tests.

    Constructed as a factory (`StubLiveSource(payload)` returns a callable
    with the same `LiveSource(game_id=...)` call signature used in
    `app.comparison.api`), mirroring how `tests/test_api.py` swaps in a
    `source_factory` for the live-sync endpoint.
    """

    def __init__(self, payload: dict[str, Any] | None = None, error: Exception | None = None):
        self._payload = payload
        self._error = error

    def __call__(self, *, game_id: int) -> StubLiveSource:
        self.game_id = str(game_id)
        return self

    def fetch_snapshot(self) -> dict[str, Any]:
        if self._error is not None:
            raise self._error
        assert self._payload is not None
        return self._payload


class FakeComparisonNoteProvider(ComparisonNoteProvider):
    """Records the comparison it was given and returns a canned note.

    Lets tests assert that a provider receives the exact, backend-computed
    `PregameLiveComparison` object — never raw numbers it could recompute
    or invent on its own.
    """

    def __init__(self, note: ComparisonNote | None = None) -> None:
        self.note = note or ComparisonNote(
            summary="fake summary", notable_changes=[], sample_note="fake sample note"
        )
        self.received_comparisons: list[PregameLiveComparison] = []

    def generate_note(self, comparison: PregameLiveComparison) -> ComparisonNote:
        self.received_comparisons.append(comparison)
        return self.note


class FakeGenAIClient:
    """Stands in for `google.genai.Client` in Gemini boundary tests."""

    def __init__(self, response_text: str | None = None, error: Exception | None = None):
        self._response_text = response_text
        self._error = error
        self.models = self  # so `client.models.generate_content(...)` works

    def generate_content(self, **_kwargs: Any) -> SimpleNamespace:
        if self._error is not None:
            raise self._error
        return SimpleNamespace(text=self._response_text)
