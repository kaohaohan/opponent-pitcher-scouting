"""Gemini-backed `ComparisonNoteProvider`.

Gemini receives the `PregameLiveComparison` serialized to JSON and nothing
else, the same boundary discipline as `app.pregame.llm.gemini`: no
database session, no source client, no way to query anything on its own.
Unlike the pregame brief, the response is constrained to a JSON schema
(`ComparisonNote`) via the SDK's structured-output mode, so a malformed
reply is a distinct, detectable failure rather than silently-wrong prose.

`GeminiConfigurationError`/`GeminiRequestError` are reused directly from
`app.pregame.llm.gemini` — generic failure modes (no API key, the API call
itself failed) that mean the same thing here as they do for the pregame
brief, so there is no reason to redefine them.
"""

from __future__ import annotations

from google import genai
from google.genai import types
from pydantic import ValidationError

from ...config import settings
from ...pregame.llm.gemini import GeminiConfigurationError, GeminiRequestError
from ..schemas import ComparisonNote, PregameLiveComparison
from .base import ComparisonNoteProvider

DEFAULT_MODEL = "gemini-3.6-flash"

#: Gemini calls are user-triggered (an on-demand "Generate AI Note"
#: button), not polled — an explicit timeout means a slow upstream fails
#: fast instead of hanging the request indefinitely. Phase 2's brief call
#: has no such timeout; this closes that gap for this new code path only.
_REQUEST_TIMEOUT_MS = 15_000

_SYSTEM_INSTRUCTION = (
    "You are a baseball analyst writing a concise in-game scouting note. "
    "You are given ONLY precomputed, structured pregame-vs-live pitch data "
    "for one pitcher. Every percentage, velocity, and delta was calculated "
    "by backend code; you must not recompute, estimate, or invent any "
    "number that is not already present in the data. Each row carries an "
    "'is_notable' flag — only mention a pitch type in 'notable_changes' "
    "when its row has is_notable=true; rows with is_notable=false or "
    "status='insufficient_sample' must never be described as a trend. "
    "Reflect 'overall_live_status' and 'limitations' in 'sample_note': if "
    "the live sample is insufficient, say so plainly and keep "
    "'notable_changes' empty. Keep 'summary' to two or three sentences."
)


class GeminiMalformedResponseError(RuntimeError):
    """Raised when Gemini's structured response fails to parse or
    validate as a `ComparisonNote`. Distinct from `GeminiRequestError`
    (the request itself failing) since this is a Phase 5-only failure
    mode: the pregame brief has no response schema to violate."""


class GeminiComparisonProvider(ComparisonNoteProvider):
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self._model = model

    def generate_note(self, comparison: PregameLiveComparison) -> ComparisonNote:
        api_key = settings.gemini_api_key
        if not api_key:
            raise GeminiConfigurationError(
                "GEMINI_API_KEY is not set; cannot generate a comparison note."
            )

        client = genai.Client(api_key=api_key)
        try:
            response = client.models.generate_content(
                model=self._model,
                contents=comparison.model_dump_json(),
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=ComparisonNote,
                    http_options=types.HttpOptions(timeout=_REQUEST_TIMEOUT_MS),
                ),
            )
        except Exception as exc:
            raise GeminiRequestError(f"Gemini request failed: {exc}") from exc

        try:
            return ComparisonNote.model_validate_json(response.text)
        except (ValidationError, ValueError) as exc:
            raise GeminiMalformedResponseError(
                f"Gemini returned a response that did not match the expected "
                f"schema: {exc}"
            ) from exc
