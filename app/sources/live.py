"""One-shot adapter for MLB's live feed.

The caller owns polling. Each source instance fetches one snapshot, walks its
completed plays oldest-first, and then terminates. Re-reading a snapshot is
safe because the database is the idempotency authority.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx

from .base import PlateAppearanceSource, RawEvent


class LiveSourceError(RuntimeError):
    """A feed-level failure that should be translated by the HTTP API."""


class LiveGameNotFound(LiveSourceError):
    """MLB returned 404 for the requested game."""


class LiveFeedError(LiveSourceError):
    """MLB was unavailable or returned an unusable response."""


class LiveSource(PlateAppearanceSource):
    """Fetches one MLB game snapshot and emits completed watched PAs.

    Args:
        game_id: The game to follow.
        watched_player_ids: External player ids to emit events for.
        client: Optional injected client, useful for deterministic tests.
    """

    name = "live"

    def __init__(
        self,
        game_id: str | int,
        watched_player_ids: tuple[str, ...] = (),
        client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.game_id = str(game_id)
        self.watched_player_ids = frozenset(str(player_id) for player_id in watched_player_ids)
        self._client = client
        self.timeout = timeout
        self.game_state: str | None = None
        self.game_status: str | None = None

    def events(self) -> Iterator[RawEvent]:
        payload = self._fetch()
        self._set_game_status(payload)
        plays = payload.get("liveData", {}).get("plays", {}).get("allPlays", [])
        if not isinstance(plays, list):
            raise LiveFeedError("MLB feed liveData.plays.allPlays is not a list")
        for play in sorted(plays, key=lambda item: self._at_bat_sort_key(item)):
            event = self._normalize_play(play, payload)
            if event is not None:
                yield event

    def _fetch(self) -> dict[str, Any]:
        url = f"https://statsapi.mlb.com/api/v1.1/game/{self.game_id}/feed/live"
        client = self._client or httpx.Client(timeout=self.timeout)
        close_client = self._client is None
        try:
            try:
                response = client.get(url)
            except httpx.HTTPError as exc:
                raise LiveFeedError(f"MLB feed request failed: {exc}") from exc
            if response.status_code == 404:
                raise LiveGameNotFound(f"MLB game {self.game_id} was not found")
            if response.status_code >= 400:
                raise LiveFeedError(f"MLB feed returned HTTP {response.status_code}")
            try:
                payload = response.json()
            except ValueError as exc:
                raise LiveFeedError("MLB feed returned invalid JSON") from exc
        finally:
            if close_client:
                client.close()
        if not isinstance(payload, dict):
            raise LiveFeedError("MLB feed top level must be an object")
        game_data = payload.get("gameData")
        live_data = payload.get("liveData")
        if not isinstance(game_data, dict) or not isinstance(live_data, dict):
            raise LiveFeedError("MLB feed is missing gameData or liveData")
        if not isinstance(game_data.get("status"), dict):
            raise LiveFeedError("MLB feed is missing gameData.status")
        if not isinstance(game_data.get("teams"), dict):
            raise LiveFeedError("MLB feed is missing gameData.teams")
        plays = live_data.get("plays")
        if not isinstance(plays, dict) or not isinstance(plays.get("allPlays"), list):
            raise LiveFeedError("MLB feed is missing liveData.plays.allPlays")
        return payload

    def _set_game_status(self, payload: dict[str, Any]) -> None:
        status = payload["gameData"]["status"]
        self.game_state = status.get("abstractGameState")
        self.game_status = status.get("detailedState")

    @staticmethod
    def _at_bat_sort_key(play: Any) -> int:
        if not isinstance(play, dict):
            return 10**9
        about = play.get("about")
        value = about.get("atBatIndex") if isinstance(about, dict) else None
        return value if isinstance(value, int) else 10**9

    def _normalize_play(self, play: Any, payload: dict[str, Any]) -> RawEvent | None:
        if not isinstance(play, dict):
            return None
        about = play.get("about") if isinstance(play.get("about"), dict) else {}
        matchup = play.get("matchup") if isinstance(play.get("matchup"), dict) else {}
        batter = matchup.get("batter") if isinstance(matchup.get("batter"), dict) else {}
        batter_id = batter.get("id")
        if batter_id is None or str(batter_id) not in self.watched_player_ids:
            return None
        if about.get("isComplete") is not True:
            return None

        game_data = payload["gameData"]
        teams = game_data.get("teams", {})
        top = about.get("isTopInning") is True
        team_data = teams.get("away" if top else "home")
        team = team_data.get("name") if isinstance(team_data, dict) else None
        result_data = play.get("result") if isinstance(play.get("result"), dict) else {}
        pitcher = matchup.get("pitcher") if isinstance(matchup.get("pitcher"), dict) else {}
        terminal = self._terminal_pitch(play)
        details = terminal.get("details") if terminal else {}
        pitch_type = (
            details.get("type", {}).get("description")
            if isinstance(details, dict) and isinstance(details.get("type"), dict)
            else None
        )
        pitch_data = terminal.get("pitchData") if terminal else {}
        hit_data = terminal.get("hitData") if terminal else {}
        return {
            "game_id": self.game_id,
            "external_player_id": str(batter_id),
            "player_name": batter.get("fullName"),
            "team": team,
            "at_bat_index": about.get("atBatIndex"),
            "inning": about.get("inning"),
            "result": result_data.get("event"),
            "pitcher": pitcher.get("fullName"),
            "is_complete": True,
            "pitch_type": pitch_type,
            "pitch_velocity": (
                pitch_data.get("startSpeed") if isinstance(pitch_data, dict) else None
            ),
            "exit_velocity": hit_data.get("launchSpeed") if isinstance(hit_data, dict) else None,
            "launch_angle": hit_data.get("launchAngle") if isinstance(hit_data, dict) else None,
        }

    @staticmethod
    def _terminal_pitch(play: dict[str, Any]) -> dict[str, Any] | None:
        events = play.get("playEvents")
        if not isinstance(events, list):
            return None
        for event in reversed(events):
            if isinstance(event, dict) and event.get("isPitch") is True:
                return event
        return None
