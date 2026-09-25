"""Unit tests for `app.llm_guard` — the backend check that rejects Gemini
prose describing pitch intent/execution rather than where a pitch finished."""

from __future__ import annotations

import pytest

from app.llm_guard import (
    LLMPolicyViolationError,
    ensure_no_banned_phrases,
    find_banned_phrases,
)

BANNED_EXAMPLES = [
    "That was a mistake pitch over the plate.",
    "He has made a few mistakes with his fastball location.",
    "That fastball was clearly mistaken for a strike.",
    "He missed his spot up and away.",
    "The pitch missed her target badly.",
    "The pitch missed their location.",
    "The pitcher missed the spot on that slider.",
    "This was intended to be a backdoor slider.",
    "He meant to bury that curveball.",
    "He tried to paint the corner.",
    "He wanted to go up and in.",
    "He has lost his command tonight.",
    "The pitcher lost command of the fastball.",
    "The catcher couldn't locate a good target.",
    "The catcher could not locate the target.",
]


@pytest.mark.parametrize("text", BANNED_EXAMPLES)
def test_find_banned_phrases_detects_each_banned_example(text):
    assert find_banned_phrases(text) != []


@pytest.mark.parametrize(
    "text",
    [
        "MISTAKE pitch.",
        "He MISSED HIS SPOT badly.",
        "This was INTENDED as a slider.",
        "He Meant To throw a fastball.",
        "He TRIED TO hit the corner.",
        "He WANTED TO go inside.",
        "He LOST COMMAND tonight.",
    ],
)
def test_find_banned_phrases_is_case_insensitive(text):
    assert find_banned_phrases(text) != []


def test_find_banned_phrases_detects_curly_apostrophe_variant():
    text = "The catcher couldn’t locate a target."
    matches = find_banned_phrases(text)
    assert matches != []
    assert "locate" in matches[0]


@pytest.mark.parametrize(
    "text",
    [
        "That was an intentional walk.",
        "He drew an Intent Walk in the seventh.",
        "The pitch caught the heart of the zone.",
        "He pitched with good command tonight.",
        "",
    ],
)
def test_find_banned_phrases_allows_safe_text(text):
    assert find_banned_phrases(text) == []


def test_ensure_no_banned_phrases_raises_with_matched_phrases():
    with pytest.raises(LLMPolicyViolationError) as exc_info:
        ensure_no_banned_phrases(["He clearly missed his spot there."])
    assert exc_info.value.phrases
    assert any("missed his spot" in phrase.lower() for phrase in exc_info.value.phrases)


def test_ensure_no_banned_phrases_passes_for_clean_text():
    ensure_no_banned_phrases(["He threw a first-pitch strike.", "Good command tonight."])
