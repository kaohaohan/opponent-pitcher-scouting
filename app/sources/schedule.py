"""One-shot adapter for MLB's schedule endpoint.

Lets the frontend list a date's games so a user can pick one without already
knowing its gamePk. Mirrors `LiveSource`'s fetch/error conventions; this
source never persists anything and never feeds the plate-appearance pipeline.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..schemas import ScheduleGameRead, TeamRead


class ScheduleSourceError(RuntimeError):
    """MLB's schedule feed was unavailable or returned an unusable response."""


class ScheduleSource:
    """Fetches MLB's schedule for one date."""

    def __init__(self, client: httpx.Client | None = None, timeout: float = 10.0) -> None:
        self._client = client
        self.timeout = timeout

    def games_for_date(self, date: str) -> list[ScheduleGameRead]:
        payload = self._fetch(date)
        dates = payload.get("dates", [])
        if not isinstance(dates, list):
            raise ScheduleSourceError("MLB schedule dates is not a list")
        games: list[ScheduleGameRead] = []
        for date_entry in dates:
            if not isinstance(date_entry, dict):
                continue
            entry_games = date_entry.get("games", [])
            if not isinstance(entry_games, list):
                continue
            for game in entry_games:
                parsed = self._parse_game(game, date)
                if parsed is not None:
                    games.append(parsed)
        return games

    def _fetch(self, date: str) -> dict[str, Any]:
        url = "https://statsapi.mlb.com/api/v1/schedule"
        params = {"sportId": 1, "date": date}
        client = self._client or httpx.Client(timeout=self.timeout)
        close_client = self._client is None
        try:
            try:
                response = client.get(url, params=params)
            except httpx.HTTPError as exc:
                raise ScheduleSourceError(f"MLB schedule request failed: {exc}") from exc
            if response.status_code >= 400:
                raise ScheduleSourceError(
                    f"MLB schedule returned HTTP {response.status_code}"
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise ScheduleSourceError("MLB schedule returned invalid JSON") from exc
        finally:
            if close_client:
                client.close()
        if not isinstance(payload, dict):
            raise ScheduleSourceError("MLB schedule top level must be an object")
        return payload

    @staticmethod
    def _parse_game(game: Any, date: str) -> ScheduleGameRead | None:
        if not isinstance(game, dict):
            return None
        game_pk = game.get("gamePk")
        teams = game.get("teams") if isinstance(game.get("teams"), dict) else {}
        away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
        home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
        away_team = away.get("team") if isinstance(away.get("team"), dict) else {}
        home_team = home.get("team") if isinstance(home.get("team"), dict) else {}
        if (
            game_pk is None
            or not isinstance(away_team.get("name"), str)
            or not isinstance(home_team.get("name"), str)
        ):
            return None
        status = game.get("status") if isinstance(game.get("status"), dict) else {}
        game_date_iso = game.get("gameDate")
        return ScheduleGameRead(
            game_id=str(game_pk),
            game_date=date,
            away_team=TeamRead(id=away_team.get("id"), name=away_team["name"]),
            home_team=TeamRead(id=home_team.get("id"), name=home_team["name"]),
            status=status.get("detailedState") or status.get("abstractGameState") or "Unknown",
            start_time=str(game_date_iso) if isinstance(game_date_iso, str) else None,
            away_score=away.get("score") if isinstance(away.get("score"), int) else None,
            home_score=home.get("score") if isinstance(home.get("score"), int) else None,
        )
