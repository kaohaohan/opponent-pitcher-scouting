"""Shared fixtures: an isolated in-memory database per test."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import DEFAULT_FIXTURE
from app.db import Base
from app.processing import PlateAppearanceProcessor
from app.sources import clear_live_snapshot_cache


@pytest.fixture(autouse=True)
def _isolated_live_snapshot_cache() -> Iterator[None]:
    """Keep the process-wide live feed snapshot cache from leaking across tests."""
    clear_live_snapshot_cache()
    yield
    clear_live_snapshot_cache()


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    """A fresh in-memory SQLite database, shared across connections in one test."""
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False, future=True)
    finally:
        engine.dispose()


@pytest.fixture()
def processor(session_factory: sessionmaker[Session]) -> PlateAppearanceProcessor:
    return PlateAppearanceProcessor(session_factory)


@pytest.fixture()
def fixture_path() -> Path:
    return DEFAULT_FIXTURE


def make_raw_event(**overrides: Any) -> dict[str, Any]:
    """A complete, valid raw event; override single fields per test."""
    event: dict[str, Any] = {
        "external_player_id": "mock-696285",
        "player_name": "Hao-Yu Lee",
        "team": "Philadelphia Phillies",
        "game_id": "2025-08-14-WSH-PHI",
        "at_bat_index": 1,
        "inning": 1,
        "result": "Groundout",
        "pitcher": "Mitchell Parker",
        "pitch_type": "Sinker",
        "pitch_velocity": 92.4,
        "exit_velocity": 87.6,
        "launch_angle": -4.0,
        "is_complete": True,
    }
    event.update(overrides)
    return event
