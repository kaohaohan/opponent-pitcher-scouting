"""Gemini-backed `LLMProvider`.

Gemini receives the `PregameContext` serialized to JSON and nothing else —
no database session, no Statcast client, no way to query anything on its
own. The system instruction tells it explicitly that every number was
precomputed and that `insufficient_sample` buckets are caveats, never
trends.
"""

from __future__ import annotations

from google import genai
from google.genai import types

from ...config import settings
from ..schemas import PregameContext
from .base import LLMProvider

DEFAULT_MODEL = "gemini-3.6-flash"

_SYSTEM_INSTRUCTION = (
    "You are a baseball analyst writing a concise pre-game scouting brief. "
    "You are given ONLY precomputed, structured pitch-usage data for one "
    "pitcher. Every count, percentage, and sample size was calculated by "
    "backend code; you must not recompute, estimate, or invent any number "
    "that is not already present in the data. Each usage figure carries a "
    "status of 'sufficient' or 'insufficient_sample'. Never describe an "
    "'insufficient_sample' figure as a tendency, pattern, or something the "
    "pitcher is likely to do — mention it, if at all, only as an "
    "observation with too little data to draw a conclusion. Read the "
    "'limitations' list and reflect those caveats in the brief rather than "
    "ignoring them."
)


class GeminiConfigurationError(RuntimeError):
    """Raised when `GEMINI_API_KEY` is not configured."""


class GeminiRequestError(RuntimeError):
    """Raised when the Gemini API call itself fails."""


class GeminiProvider(LLMProvider):
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self._model = model

    def generate_brief(self, context: PregameContext) -> str:
        api_key = settings.gemini_api_key
        if not api_key:
            raise GeminiConfigurationError(
                "GEMINI_API_KEY is not set; cannot generate a pre-game brief."
            )

        client = genai.Client(api_key=api_key)
        try:
            response = client.models.generate_content(
                model=self._model,
                contents=context.model_dump_json(),
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_INSTRUCTION
                ),
            )
        except Exception as exc:
            raise GeminiRequestError(f"Gemini request failed: {exc}") from exc
        return response.text
