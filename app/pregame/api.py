"""POST /api/pregame/brief — the only Phase 2 HTTP surface.

Stateless: nothing here reads from or writes to the SQLite database used by
Phase 1. One request means one fetch, one aggregation pass, one LLM call.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from .context import PregameContextBuilder
from .llm.base import LLMProvider
from .llm.gemini import GeminiConfigurationError, GeminiProvider, GeminiRequestError
from .schemas import PregameBriefRequest, PregameBriefResponse
from .sources.base import PitchDataSource
from .sources.statcast import StatcastFetchError, StatcastPitchSource

router = APIRouter(prefix="/api/pregame", tags=["pregame"])


def get_pitch_source() -> PitchDataSource:
    return StatcastPitchSource()


def get_llm_provider() -> LLMProvider:
    return GeminiProvider()


@router.post("/brief", response_model=PregameBriefResponse)
def generate_pregame_brief(
    request: PregameBriefRequest,
    source: PitchDataSource = Depends(get_pitch_source),
    llm: LLMProvider = Depends(get_llm_provider),
) -> PregameBriefResponse:
    """Fetch, aggregate, guard, and describe one pitcher's recent pitches."""
    try:
        records = source.fetch_pitcher_pitches(
            request.pitcher_id, request.start_date, request.end_date
        )
    except StatcastFetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    context = PregameContextBuilder().build(
        pitcher_id=request.pitcher_id,
        start_date=request.start_date,
        end_date=request.end_date,
        records=records,
    )

    try:
        brief = llm.generate_brief(context)
    except GeminiConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except GeminiRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    return PregameBriefResponse(context=context, brief=brief)
