"""Phase 5 HTTP surface: the pregame-vs-live pitch comparison for one
watched pitcher, plus an on-demand AI note over it.

Two routes, deliberately not one bundled endpoint: the comparison route
never calls Gemini, so it is safe to poll as often as the existing
live-sync/events/alerts queries, and stays a 200 with the full numeric
table even when Gemini is unavailable, times out, or replies with
something that doesn't parse. The note route is the only one that ever
calls Gemini, and is meant to be triggered on demand (a "Generate AI
Note" click), not polled. Both compose existing Phase 2/3 building blocks
(`StatcastPitchSource`, `LiveSource`) rather than reimplementing either
fetch.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from ..pregame.api import get_pitch_source
from ..pregame.context import PregameContextBuilder
from ..pregame.sources.base import PitchDataSource
from ..pregame.sources.statcast import StatcastFetchError
from ..sources.live import LiveGameNotFound, LiveSource, LiveSourceError
from .compare import build_comparison
from .live_metrics import compute_live_pitcher_metrics
from .llm.base import ComparisonNoteProvider
from .llm.gemini import (
    GeminiComparisonProvider,
    GeminiConfigurationError,
    GeminiMalformedResponseError,
    GeminiRequestError,
)
from .schemas import ComparisonNote, PregameLiveComparison

router = APIRouter(prefix="/api/live/games", tags=["comparison"])

#: Reused verbatim from `app.pregame.api` so a test's
#: `app.dependency_overrides[get_pitch_source] = ...` swaps the Statcast
#: source for both the pregame brief route and this one — one DI seam,
#: not two independent ones that happen to look alike.


def get_comparison_note_provider() -> ComparisonNoteProvider:
    return GeminiComparisonProvider()


def _build_comparison(
    game_id: int,
    pitcher_id: int,
    start_date: date,
    end_date: date,
    source: PitchDataSource,
) -> PregameLiveComparison:
    """Fetch both halves and assemble the deterministic comparison.

    Shared by both routes below: the note route needs the exact same
    comparison the numeric route would have returned, not a second,
    possibly-different computation of it.
    """
    live_source = LiveSource(game_id=game_id)
    try:
        payload = live_source.fetch_snapshot()
    except LiveGameNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LiveSourceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    live_metrics = compute_live_pitcher_metrics(payload, pitcher_id)

    try:
        records = source.fetch_pitcher_pitches(pitcher_id, start_date, end_date)
    except StatcastFetchError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    baseline = PregameContextBuilder().build(pitcher_id, start_date, end_date, records)

    return build_comparison(
        game_id=live_source.game_id,
        pitcher_id=pitcher_id,
        baseline_start_date=start_date,
        baseline_end_date=end_date,
        baseline=baseline,
        live=live_metrics,
    )


@router.get(
    "/{game_id}/pitchers/{pitcher_id}/comparison",
    response_model=PregameLiveComparison,
)
def get_pregame_live_comparison(
    game_id: int,
    pitcher_id: int,
    start_date: date,
    end_date: date,
    source: PitchDataSource = Depends(get_pitch_source),
) -> PregameLiveComparison:
    """Deterministic pregame-vs-live pitch mix for one pitcher.

    Zero pregame pitches, zero live pitches, or both are not errors —
    they're reported as `baseline_available`/`live_available` flags with
    an explanatory entry in `limitations`. Only an actual fetch failure
    (game not found, MLB feed down, Statcast down) is an HTTP error. Never
    calls Gemini — safe to poll.
    """
    return _build_comparison(game_id, pitcher_id, start_date, end_date, source)


@router.post(
    "/{game_id}/pitchers/{pitcher_id}/comparison/note",
    response_model=ComparisonNote,
)
def generate_comparison_note(
    game_id: int,
    pitcher_id: int,
    start_date: date,
    end_date: date,
    source: PitchDataSource = Depends(get_pitch_source),
    llm: ComparisonNoteProvider = Depends(get_comparison_note_provider),
) -> ComparisonNote:
    """An on-demand AI explanation of the same comparison the GET route
    returns. Recomputes it internally so this endpoint can be called
    without the client having called the GET route first.

    A Gemini failure here (no key, request failure, malformed response)
    never affects the GET route — the two are entirely separate requests
    against separate computations of the deterministic numbers, so the
    numeric table is never blocked on this endpoint's success.
    """
    comparison = _build_comparison(game_id, pitcher_id, start_date, end_date, source)
    try:
        return llm.generate_note(comparison)
    except GeminiConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except (GeminiRequestError, GeminiMalformedResponseError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
