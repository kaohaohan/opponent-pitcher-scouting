"""Guards Gemini output against intent/execution vocabulary.

Statcast and the MLB live feed record where a pitch finished, not what the
catcher called or what the pitcher meant to do. The system instructions in
`app.pregame.llm.gemini` and `app.comparison.llm.gemini` already ask the
model to avoid describing intent or execution ("mistake pitch", "missed his
spot", "intended", "meant to", "lost command") — this module is the backend
enforcement of that boundary: it scans generated text for that vocabulary so
a violation is caught and rejected rather than silently reaching a user.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

#: Curly single quotes/apostrophes, normalized to a plain `'` before
#: matching so "couldn't locate" is caught regardless of which apostrophe
#: character the model (or a fake in tests) used.
_CURLY_APOSTROPHES = str.maketrans({"’": "'", "‘": "'"})

_BANNED_PATTERNS = [
    re.compile(r"\bmistakes?\b", re.IGNORECASE),
    re.compile(r"\bmistaken\b", re.IGNORECASE),
    re.compile(
        r"\bmissed\s+(?:his|her|their|the)?\s*(?:spot|target|location)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bintended\b", re.IGNORECASE),
    re.compile(r"\bmeant to\b", re.IGNORECASE),
    re.compile(r"\btried to\b", re.IGNORECASE),
    re.compile(r"\bwanted to\b", re.IGNORECASE),
    re.compile(r"\blost\s+(?:his|her|their)?\s*command\b", re.IGNORECASE),
    re.compile(r"\bcould(?:n't|n’t| not) locate\b", re.IGNORECASE),
]


def find_banned_phrases(text: str) -> list[str]:
    """Every intent/execution phrase found in `text`, in the order they
    appear. Empty when `text` is clean.

    Matching is case-insensitive with word boundaries, so "intentional" and
    "Intent Walk" never match `\\bintended\\b`, and bare "command" never
    matches the "lost command" pattern on its own.
    """
    normalized = text.translate(_CURLY_APOSTROPHES)
    matches: list[tuple[int, str]] = []
    for pattern in _BANNED_PATTERNS:
        for match in pattern.finditer(normalized):
            matches.append((match.start(), match.group(0)))
    matches.sort(key=lambda item: item[0])
    return [phrase for _, phrase in matches]


class LLMPolicyViolationError(RuntimeError):
    """Raised when generated text contains banned intent/execution vocabulary.

    Carries the matched phrases so a caller can report exactly what tripped
    the guard.
    """

    def __init__(self, phrases: list[str]) -> None:
        self.phrases = phrases
        super().__init__(
            "LLM output contains disallowed intent/execution vocabulary: "
            + ", ".join(phrases)
        )


def ensure_no_banned_phrases(texts: Iterable[str]) -> None:
    """Raise `LLMPolicyViolationError` if any string in `texts` contains a
    banned phrase. Checks every string before raising, so the error names
    every violation across all of them, not just the first."""
    found: list[str] = []
    for text in texts:
        found.extend(find_banned_phrases(text))
    if found:
        raise LLMPolicyViolationError(found)
