"""Gemini-backed `ComparisonNoteProvider`.

Gemini receives a `ComparisonNoteInput` serialized to JSON: deterministic
pitch comparison data plus backend-computed game outcomes, and nothing else.
It follows the same boundary discipline as `app.pregame.llm.gemini`: no
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
from pydantic import BaseModel, Field, ValidationError

from ...config import settings
from ...pregame.llm.gemini import GeminiConfigurationError, GeminiRequestError
from ..schemas import ComparisonNote, ComparisonNoteInput
from .base import ComparisonNoteProvider

DEFAULT_MODEL = "gemini-3.6-flash"

#: Gemini calls are user-triggered (an on-demand "Generate AI Note"
#: button), not polled — an explicit timeout means a slow upstream fails
#: fast instead of hanging the request indefinitely. Phase 2's brief call
#: has no such timeout; this closes that gap for this new code path only.
_REQUEST_TIMEOUT_MS = 15_000

_SYSTEM_INSTRUCTION = (
    "You are a baseball analyst writing a concise in-game scouting note. "
    "You are given ONLY precomputed, structured data for one pitcher: a "
    "pregame-vs-live pitch comparison and an outcome_context computed from "
    "the selected pitcher's completed plate appearances. The outcome context "
    "contains descriptive game results, not predictions or explanations. "
    "Include the most relevant available outcome facts in 'summary'. Keep "
    "'notable_changes' limited to pitch changes backed by 'signals'. Use "
    "outcome_context limitations to qualify missing outcome measurements. "
    "Every percentage, velocity, count, and delta was calculated "
    "by backend code; you must not recompute, estimate, or invent any "
    "number that is not already present in the data. "
    "The 'signals' list is the ONLY source of changes you may cite in "
    "'notable_changes': mention a pitch type there only if it has a "
    "matching entry in 'signals', identified by its 'pitch_type'. Never "
    "cite a change for a pitch type that has no signal, even if its row's "
    "numbers look different — an absent signal means the gap did not "
    "clear the sample-size or magnitude bar to be worth mentioning. "
    "A signal's 'level' controls how you phrase it: an 'alert' can be "
    "described as a clear change; a 'watch' must be phrased more "
    "tentatively, as early or as something to continue monitoring (e.g. "
    "'starting to lean more on...', 'worth continuing to watch'), never "
    "as a settled trend. Never speculate about WHY a number moved or an "
    "outcome occurred — no guesses about mechanics, fatigue, strategy, pitch "
    "selection, or matchups. Never describe a pitcher's intent or execution "
    "— no 'mistake', 'missed his spot', 'intended', 'meant to', or 'lost "
    "command' — describe only where the pitch finished and the observed "
    "outcome. Report outcomes only as observed facts. Do not "
    "calculate rates or totals from outcome_context; use the supplied values. "
    "The hard-hit count uses the supplied hard_hit_threshold_mph. If the "
    "maximum exit velocity is null, say it is unavailable rather than zero. "
    "When a signal's 'today_value' is 0 for a "
    "usage metric, describe it as the pitcher having 'not thrown that "
    "pitch yet today', not as a percentage drop to zero. "
    "Reflect 'overall_live_status' and 'limitations' in 'sample_note': if "
    "the live sample is insufficient, say so plainly and keep "
    "'notable_changes' empty regardless of what 'signals' contains. Keep "
    "'summary' to two or three sentences."
)


class GeminiMalformedResponseError(RuntimeError):
    """Raised when Gemini's structured response fails to parse or
    validate as a `ComparisonNote`. Distinct from `GeminiRequestError`
    (the request itself failing) since this is a Phase 5-only failure
    mode: the pregame brief has no response schema to violate."""


class _NotableChangeSchema(BaseModel):
    metric: str
    description: str


class _ComparisonNoteSchema(BaseModel):
    """The shape sent to Gemini as `response_schema`.

    Mirrors `ComparisonNote` but deliberately omits `extra="forbid"`:
    pydantic renders that as `additionalProperties: false`, which the Gemini
    API rejects (400 "Unknown name additional_properties"). The reply is
    still validated against the strict `ComparisonNote` afterwards, so
    nothing is loosened on our side of the boundary.
    """

    summary: str
    notable_changes: list[_NotableChangeSchema] = Field(default_factory=list)
    sample_note: str


class GeminiComparisonProvider(ComparisonNoteProvider):
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self._model = model

    def generate_note(self, comparison: ComparisonNoteInput) -> ComparisonNote:
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
                    response_schema=_ComparisonNoteSchema,
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
