"""HTTP read endpoints plus the development replay trigger.

Thin on purpose: the routes translate query parameters into repository calls and
ORM rows into response models. No domain logic lives here.
"""

from __future__ import annotations

from datetime import date as date_cls

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import repository
from ..db import SessionFactory, get_session
from ..processing import PlateAppearanceProcessor
from ..schemas import (
    AlertRead,
    GameParticipantsRead,
    LiveSyncReport,
    LiveSyncRequest,
    PlateAppearanceRead,
    PlayerRead,
    ReplayReport,
    ScheduleGameRead,
    WatchRole,
)
from ..sources import (
    LiveGameNotFound,
    LiveSource,
    LiveSourceError,
    ReplaySource,
    ScheduleSource,
    ScheduleSourceError,
)

router = APIRouter(prefix="/api", tags=["watch"])


@router.get("/players", response_model=list[PlayerRead])
def get_players(session: Session = Depends(get_session)) -> list[PlayerRead]:
    """Players we have seen plate appearances for."""
    return [PlayerRead.model_validate(player) for player in repository.list_players(session)]


@router.get("/events", response_model=list[PlateAppearanceRead])
def get_events(
    game_id: str | None = None,
    player_id: int | None = None,
    batter_id: str | None = None,
    pitcher_id: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> list[PlateAppearanceRead]:
    """Stored plate appearances, oldest first within each game."""
    rows = repository.list_plate_appearances(
        session,
        game_id=game_id,
        player_id=player_id,
        batter_id=batter_id,
        pitcher_id=pitcher_id,
        limit=limit,
    )
    return [PlateAppearanceRead.model_validate(row) for row in rows]


@router.get("/alerts", response_model=list[AlertRead])
def get_alerts(
    rule_type: str | None = None,
    subject_role: WatchRole | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> list[AlertRead]:
    """Alerts the rule engine has raised, newest first."""
    rows = repository.list_alerts(
        session, rule_type=rule_type, subject_role=subject_role, limit=limit
    )
    return [AlertRead.model_validate(row) for row in rows]


@router.post("/replay", response_model=ReplayReport, status_code=status.HTTP_200_OK)
def trigger_replay(fixture_path: str | None = None) -> ReplayReport:
    """Replay a historical fixture through the pipeline. Development/demo only.

    Safe to call repeatedly: ingestion is idempotent, so a second replay reports
    every plate appearance as a duplicate and creates no further alerts.
    """
    source = (
        ReplaySource(fixture_path) if fixture_path else ReplaySource.from_default_fixture()
    )
    if not source.fixture_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fixture not found: {source.fixture_path}",
        )
    processor = PlateAppearanceProcessor(SessionFactory)
    return processor.process_source(source)


@router.post("/live/sync", response_model=LiveSyncReport)
def sync_live(request: LiveSyncRequest) -> LiveSyncReport:
    """Fetch one MLB snapshot and ingest completed PAs for watched players."""
    source = LiveSource(
        game_id=request.game_id,
        batter_ids=tuple(str(player_id) for player_id in request.batter_ids),
        pitcher_ids=tuple(str(player_id) for player_id in request.pitcher_ids),
    )
    processor = PlateAppearanceProcessor(SessionFactory)
    try:
        report = processor.process_source(source, propagate_source_errors=True)
    except LiveGameNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LiveSourceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return LiveSyncReport(
        **report.model_dump(),
        game_id=source.game_id,
        game_state=source.game_state,
        game_status=source.game_status,
    )


@router.get("/live/games", response_model=list[ScheduleGameRead])
def get_live_games(date: str = Query(...)) -> list[ScheduleGameRead]:
    """MLB's schedule for one date, so a user can pick a game without a gamePk."""
    try:
        parsed_date = date_cls.fromisoformat(date)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date must be formatted as YYYY-MM-DD",
        ) from exc
    source = ScheduleSource()
    try:
        return source.games_for_date(parsed_date.isoformat())
    except ScheduleSourceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get(
    "/live/games/{game_id}/participants",
    response_model=GameParticipantsRead,
)
def get_live_game_participants(game_id: int) -> GameParticipantsRead:
    """Discover game participants from MLB's live feed without persisting them."""
    source = LiveSource(game_id=game_id)
    try:
        return source.discover_participants()
    except LiveGameNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LiveSourceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
