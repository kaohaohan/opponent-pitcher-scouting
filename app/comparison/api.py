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
fetch. The Statcast baseline fetch itself sits behind a 6-hour in-process
TTL cache (`_fetch_baseline_records`/`clear_baseline_cache`) so that
repeated polling of the same pitcher/window doesn't repeatedly hit
Baseball Savant.
"""

from __future__ import annotations

import threading
import time
from datetime import date
from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, status

from ..llm_guard import LLMPolicyViolationError, ensure_no_banned_phrases
from ..pregame.api import get_pitch_source
from ..pregame.context import PregameContextBuilder
from ..pregame.schemas import PitchRecord
from ..pregame.sources.base import PitchDataSource
from ..pregame.sources.statcast import StatcastFetchError
from ..sources.live import LiveGameNotFound, LiveSource, LiveSourceError
from .compare import build_comparison
from .contact import ContactPitches, compute_contact_pitches
from .live_metrics import compute_live_pitcher_metrics
from .llm.base import ComparisonNoteProvider
from .llm.gemini import (
    GeminiComparisonProvider,
    GeminiConfigurationError,
    GeminiMalformedResponseError,
    GeminiRequestError,
)
from .locations import PitchLocations, compute_pitch_locations
from .outcomes import compute_pitcher_outcome_context
from .schemas import ComparisonNote, ComparisonNoteInput, PregameLiveComparison

router = APIRouter(prefix="/api/live/games", tags=["comparison"])

#: Reused verbatim from `app.pregame.api` so a test's
#: `app.dependency_overrides[get_pitch_source] = ...` swaps the Statcast
#: source for both the pregame brief route and this one — one DI seam,
#: not two independent ones that happen to look alike.

#: How long a fetched Statcast baseline stays fresh before the next caller
#: re-hits Baseball Savant. Comparison polling (~15s) re-requests the same
#: (pitcher_id, start_date, end_date) window on every poll even though the
#: baseline itself only changes once a day, so this collapses a whole
#: polling session down to one upstream fetch per window.
_BASELINE_CACHE_TTL_SECONDS = 6 * 60 * 60.0

_BaselineCacheKey = tuple[int, date, date]

# (pitcher_id, start_date, end_date) -> (fetched_at monotonic timestamp,
# records). Process-wide and in-memory only, same convention as
# `app.sources.live`'s snapshot cache: no Redis, no cross-process sharing.
_baseline_cache: dict[_BaselineCacheKey, tuple[float, list[PitchRecord]]] = {}
_baseline_cache_lock = threading.Lock()

# Notes are deliberately cached only in this process. The complete note input
# (including outcome context) is part of the key, so a changed game state gets
# a fresh note while rapid repeat clicks for the same state reuse the response.
_NOTE_CACHE_TTL_SECONDS = 60.0
_NoteCacheKey = tuple[int, int, date, date, str]
_note_cache: dict[_NoteCacheKey, tuple[float, ComparisonNote]] = {}
_note_cache_lock = threading.Lock()


def clear_baseline_cache() -> None:
    """Drop every cached Statcast baseline fetch.

    Tests use this (via an autouse fixture in `tests/comparison/conftest.py`)
    to keep runs isolated, since the cache is process-wide state shared
    across `PitchDataSource` instances.
    """
    with _baseline_cache_lock:
        _baseline_cache.clear()


def clear_comparison_note_cache() -> None:
    """Drop cached Gemini notes (used by tests and process-local resets)."""
    with _note_cache_lock:
        _note_cache.clear()


def _comparison_note_cache_key(
    game_id: int,
    pitcher_id: int,
    start_date: date,
    end_date: date,
    comparison: PregameLiveComparison,
) -> _NoteCacheKey:
    state_digest = sha256(comparison.model_dump_json().encode("utf-8")).hexdigest()
    return (game_id, pitcher_id, start_date, end_date, state_digest)


def _fetch_baseline_records(
    source: PitchDataSource, pitcher_id: int, start_date: date, end_date: date
) -> list[PitchRecord]:
    """This pitcher's Statcast pitches for the window, from the TTL cache
    when fresh. Only a successful fetch is cached — a `StatcastFetchError`
    propagates so the next call retries upstream immediately.
    """
    key = (pitcher_id, start_date, end_date)
    with _baseline_cache_lock:
        cached = _baseline_cache.get(key)
        if cached is not None:
            fetched_at, records = cached
            if time.monotonic() - fetched_at < _BASELINE_CACHE_TTL_SECONDS:
                return records

    records = source.fetch_pitcher_pitches(pitcher_id, start_date, end_date)

    with _baseline_cache_lock:
        _baseline_cache[key] = (time.monotonic(), records)
    return records


def get_comparison_note_provider() -> ComparisonNoteProvider:
    return GeminiComparisonProvider()


def build_pitcher_comparison(
    game_id: int,
    pitcher_id: int,
    start_date: date,
    end_date: date,
    source: PitchDataSource,
    live_payload: dict | None = None,
) -> PregameLiveComparison:
    """Fetch both halves and assemble the deterministic comparison.

    Shared by both routes below (the note route needs the exact same
    comparison the numeric route would have returned, not a second,
    possibly-different computation of it) and by `app.api.routes.sync_live`,
    which reuses this to evaluate pitch-mix signals for every watched
    pitcher on each live sync — not a name-mangled private helper, since it
    now has callers outside this module.
    """
    live_source = LiveSource(game_id=game_id)
    if live_payload is None:
        try:
            live_payload = live_source.fetch_snapshot()
        except LiveGameNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except LiveSourceError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    live_metrics = compute_live_pitcher_metrics(live_payload, pitcher_id)

    try:
        records = _fetch_baseline_records(source, pitcher_id, start_date, end_date)
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
    return build_pitcher_comparison(game_id, pitcher_id, start_date, end_date, source)


@router.get(
    "/{game_id}/pitchers/{pitcher_id}/locations",
    response_model=PitchLocations,
)
def get_pitch_locations(game_id: int, pitcher_id: int) -> PitchLocations:
    """Pitch locations for this outing, independent of Statcast and Gemini."""
    try:
        payload = LiveSource(game_id=game_id).fetch_snapshot()
    except LiveGameNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LiveSourceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return compute_pitch_locations(payload, pitcher_id)


@router.get(
    "/{game_id}/pitchers/{pitcher_id}/contact-pitches",
    response_model=ContactPitches,
)
def get_contact_pitches(game_id: int, pitcher_id: int) -> ContactPitches:
    """Home-run and 100+ mph contact pitches for this outing, independent
    of Statcast and Gemini."""
    try:
        payload = LiveSource(game_id=game_id).fetch_snapshot()
    except LiveGameNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LiveSourceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return compute_contact_pitches(payload, pitcher_id)


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
    """An on-demand AI explanation of the deterministic comparison plus
    game outcomes. Recomputes the comparison internally so this endpoint
    can be called without the client having called the GET route first.

    A Gemini failure here (no key, request failure, malformed response)
    never affects the GET route — the two are entirely separate requests
    against separate computations of the deterministic numbers, so the
    numeric table is never blocked on this endpoint's success.

    The generated note is also checked against `app.llm_guard` for
    intent/execution vocabulary (e.g. "mistake", "missed his spot") before
    it is returned or cached — this feed records where a pitch finished,
    not what anyone meant to throw. A violation is a 502, same as any other
    Gemini failure, and is never cached.
    """
    try:
        live_payload = LiveSource(game_id=game_id).fetch_snapshot()
    except LiveGameNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LiveSourceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    comparison = build_pitcher_comparison(
        game_id, pitcher_id, start_date, end_date, source, live_payload=live_payload
    )
    note_input = ComparisonNoteInput.model_validate(
        {
            **comparison.model_dump(),
            "outcome_context": compute_pitcher_outcome_context(
                live_payload, pitcher_id
            ).model_dump(),
        }
    )
    cache_key = _comparison_note_cache_key(
        game_id, pitcher_id, start_date, end_date, note_input
    )
    # Hold the process-local lock through generation. This intentionally
    # serializes same-process note generation so two simultaneous clicks for
    # the same state cannot both spend Gemini quota.
    with _note_cache_lock:
        cached = _note_cache.get(cache_key)
        if cached is not None:
            created_at, note = cached
            if time.monotonic() - created_at < _NOTE_CACHE_TTL_SECONDS:
                return note
            _note_cache.pop(cache_key, None)
        try:
            note = llm.generate_note(note_input)
        except GeminiConfigurationError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
        except (GeminiRequestError, GeminiMalformedResponseError) as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        try:
            ensure_no_banned_phrases(
                [note.summary, note.sample_note]
                + [change.metric for change in note.notable_changes]
                + [change.description for change in note.notable_changes]
            )
        except LLMPolicyViolationError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        _note_cache[cache_key] = (time.monotonic(), note)
        return note
