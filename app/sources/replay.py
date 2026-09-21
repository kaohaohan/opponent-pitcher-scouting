"""Replay source: reads plate appearances from a JSON fixture.

The fixture stores the game and the player once, and the plate appearances as a
list. Flattening those into per-event fields is exactly the normalization work a
real feed adapter would do, which keeps the contract honest.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..config import settings
from .base import PlateAppearanceSource, RawEvent

# Fields copied verbatim from each fixture plate appearance, if present.
_PA_FIELDS = (
    "at_bat_index",
    "inning",
    "result",
    "pitcher",
    "is_complete",
    "pitch_type",
    "pitch_velocity",
    "exit_velocity",
    "launch_angle",
)


class ReplaySource(PlateAppearanceSource):
    """Replays a historical game from disk, one plate appearance at a time."""

    name = "replay"

    def __init__(self, fixture_path: Path | str) -> None:
        self.fixture_path = Path(fixture_path)

    @classmethod
    def from_default_fixture(cls) -> ReplaySource:
        return cls(settings.replay_fixture_path)

    def events(self) -> Iterator[RawEvent]:
        payload = self._load()
        game = payload.get("game", {})
        player = payload.get("player", {})
        plate_appearances = payload.get("plate_appearances", [])

        # Replay in at-bat order regardless of how the fixture happens to be
        # written, so "sequential" means sequential in game time.
        for raw in sorted(plate_appearances, key=lambda pa: pa.get("at_bat_index", 0)):
            yield self._to_event(game, player, raw)

    def _load(self) -> dict[str, Any]:
        with self.fixture_path.open(encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _to_event(
        game: dict[str, Any], player: dict[str, Any], raw: dict[str, Any]
    ) -> RawEvent:
        event: dict[str, Any] = {
            "external_player_id": player.get("external_player_id"),
            "player_name": player.get("name"),
            "team": player.get("team"),
            "game_id": game.get("game_id"),
        }
        for field in _PA_FIELDS:
            if field in raw:
                event[field] = raw[field]
        return event
