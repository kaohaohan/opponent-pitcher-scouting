"""The LLM boundary.

A provider receives only a structured `PregameContext` and returns prose.
It must not fetch data, compute statistics, or invent values — the backend
calculates the baseball facts; the LLM communicates them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import PregameContext


class LLMProvider(ABC):
    @abstractmethod
    def generate_brief(self, context: PregameContext) -> str:
        """Turn a structured pre-game context into a prose brief."""
