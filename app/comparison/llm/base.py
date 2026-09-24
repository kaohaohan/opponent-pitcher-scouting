"""The comparison-note LLM boundary.

A provider receives a structured `ComparisonNoteInput`: a deterministic
`PregameLiveComparison` plus backend-computed `OutcomeContext`. It returns a
structured `ComparisonNote`. It must not fetch data, compute statistics,
or invent a number that isn't already in the input; it narrates signaled
pitch changes and observed outcomes only.

Distinct from `app.pregame.llm.base.LLMProvider`: that boundary is
free-text-in/free-text-out for the pregame brief. This one is
structured-in/structured-out, so the two aren't merged into one interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import ComparisonNote, ComparisonNoteInput


class ComparisonNoteProvider(ABC):
    @abstractmethod
    def generate_note(self, comparison: ComparisonNoteInput) -> ComparisonNote:
        """Turn a structured comparison into a structured note."""
