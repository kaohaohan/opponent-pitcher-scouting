"""One-shot adapter for MLB's live feed.

The caller owns polling. Each source instance fetches one snapshot, walks its
completed plays oldest-first, and then terminates. Re-reading a snapshot is
safe because the database is the idempotency authority.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx

from ..schemas import GameParticipantsRead, ParticipantRead, TeamRead, WatchRole
from ._swr_cache import SWRCache
from .base import PlateAppearanceSource, RawEvent


class LiveSourceError(RuntimeError):
    """A feed-level failure that should be translated by the HTTP API."""


class LiveGameNotFound(LiveSourceError):
    """MLB returned 404 for the requested game."""


class LiveFeedError(LiveSourceError):
    """MLB was unavailable or returned an unusable response."""


#: How long a fetched snapshot stays fresh before the next caller re-hits
#: MLB at all. Sync (~20s), comparison (~15s), and game-summary (~15s)
#: polling all share this cache, so within the window they collapse to one
#: upstream call.
LIVE_SNAPSHOT_TTL_SECONDS = 10.0

#: How long a stale snapshot may still be served (immediately, while a
#: background refresh runs) before a caller is made to wait on MLB directly.
#: This is what turns most polling stalls into a cache hit: instead of one
#: request in ten blocking for 2-9s on MLB, only a request that arrives more
#: than a minute after the last successful fetch ever blocks.
LIVE_SNAPSHOT_MAX_STALE_SECONDS = 60.0

# game_id -> payload, process-wide and in-memory only: no Redis, no
# cross-process sharing (games are few and short-lived, so this never grows
# large).
_snapshot_cache: SWRCache[str, dict[str, Any]] = SWRCache(
    fresh_ttl=LIVE_SNAPSHOT_TTL_SECONDS,
    max_stale=LIVE_SNAPSHOT_MAX_STALE_SECONDS,
)


def clear_live_snapshot_cache() -> None:
    """Drop every cached live feed snapshot.

    Tests use this (via an autouse fixture) to keep runs isolated, since the
    cache is process-wide state shared across `LiveSource` instances.
    """
    _snapshot_cache.clear()


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
        batter_ids: tuple[str, ...] = (),
        pitcher_ids: tuple[str, ...] = (),
        client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.game_id = str(game_id)
        self.watched_batter_ids = frozenset(
            str(player_id) for player_id in (*watched_player_ids, *batter_ids)
        )
        self.watched_pitcher_ids = frozenset(str(player_id) for player_id in pitcher_ids)
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

    def discover_participants(self) -> GameParticipantsRead:
        payload = self._fetch()
        self._set_game_status(payload)
        return self._discover_participants(payload)

    def fetch_snapshot(self) -> dict[str, Any]:
        """Fetch and return the raw MLB feed payload for this game.

        For callers that need pitch-level detail the normalized event
        stream discards (`app.comparison.live_metrics` is the current
        one) — everything else about this source stays one-shot and
        stateless, so a fresh snapshot is fetched on every call.
        """
        payload = self._fetch()
        self._set_game_status(payload)
        return payload

    def _fetch(self) -> dict[str, Any]:
        """Return this game's snapshot via the shared stale-while-revalidate cache.

        Only successful payloads are cached; `LiveGameNotFound` and
        `LiveFeedError` propagate without being cached, so a synchronous
        (too-stale-or-missing) call retries upstream immediately, and a
        failed background refresh just leaves the previous value in place.
        """
        return _snapshot_cache.get(self.game_id, self._fetch_from_upstream)

    def _fetch_from_upstream(self) -> dict[str, Any]:
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
        pitcher = matchup.get("pitcher") if isinstance(matchup.get("pitcher"), dict) else {}
        pitcher_id = pitcher.get("id")
        matched_roles = self._matched_roles(batter_id, pitcher_id)
        if not matched_roles:
            return None
        if about.get("isComplete") is not True:
            return None

        game_data = payload["gameData"]
        teams = game_data.get("teams", {})
        top = about.get("isTopInning") is True
        batter_team_data = teams.get("away" if top else "home")
        pitcher_team_data = teams.get("home" if top else "away")
        batter_team = (
            batter_team_data.get("name") if isinstance(batter_team_data, dict) else None
        )
        pitcher_team = (
            pitcher_team_data.get("name") if isinstance(pitcher_team_data, dict) else None
        )
        result_data = play.get("result") if isinstance(play.get("result"), dict) else {}
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
            "batter_id": str(batter_id) if batter_id is not None else None,
            "batter_name": batter.get("fullName"),
            "batter_team": batter_team,
            "pitcher_id": str(pitcher_id) if pitcher_id is not None else None,
            "pitcher_name": pitcher.get("fullName"),
            "pitcher_team": pitcher_team,
            "matched_roles": matched_roles,
            "at_bat_index": about.get("atBatIndex"),
            "inning": about.get("inning"),
            "result": result_data.get("event"),
            "is_complete": True,
            "pitch_type": pitch_type,
            "pitch_velocity": (
                pitch_data.get("startSpeed") if isinstance(pitch_data, dict) else None
            ),
            "exit_velocity": hit_data.get("launchSpeed") if isinstance(hit_data, dict) else None,
            "launch_angle": hit_data.get("launchAngle") if isinstance(hit_data, dict) else None,
        }

    def _matched_roles(self, batter_id: Any, pitcher_id: Any) -> tuple[WatchRole, ...]:
        roles: list[WatchRole] = []
        if batter_id is not None and str(batter_id) in self.watched_batter_ids:
            roles.append(WatchRole.BATTER)
        if pitcher_id is not None and str(pitcher_id) in self.watched_pitcher_ids:
            roles.append(WatchRole.PITCHER)
        return tuple(roles)

    def _discover_participants(self, payload: dict[str, Any]) -> GameParticipantsRead:
        teams = self._teams(payload)
        participants: dict[int, dict[str, Any]] = {}
        boxscore = payload.get("liveData", {}).get("boxscore")
        if isinstance(boxscore, dict):
            boxscore_teams = boxscore.get("teams")
            if boxscore_teams is not None and not isinstance(boxscore_teams, dict):
                raise LiveFeedError("MLB feed liveData.boxscore.teams must be an object")
            if isinstance(boxscore_teams, dict):
                for side in ("away", "home"):
                    self._merge_boxscore_team(participants, boxscore_teams.get(side), teams, side)
        elif boxscore is not None:
            raise LiveFeedError("MLB feed liveData.boxscore must be an object")

        plays = payload.get("liveData", {}).get("plays", {}).get("allPlays", [])
        if not isinstance(plays, list):
            raise LiveFeedError("MLB feed liveData.plays.allPlays is not a list")
        for play in plays:
            if isinstance(play, dict):
                self._merge_observed_play(participants, play, teams)

        return GameParticipantsRead(
            game_id=self.game_id,
            game_state=self.game_state,
            game_status=self.game_status,
            teams={side: TeamRead(**team) for side, team in teams.items()},
            participants=[
                ParticipantRead(
                    player_id=player_id,
                    name=data["name"],
                    team_id=data.get("team_id"),
                    team_name=data["team_name"],
                    team_side=data["team_side"],
                    roles=sorted(data["roles"]),
                )
                for player_id, data in sorted(
                    participants.items(),
                    key=lambda item: (item[1]["team_side"], item[1]["name"], item[0]),
                )
            ],
        )

    def _teams(self, payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        game_teams = payload["gameData"]["teams"]
        teams: dict[str, dict[str, Any]] = {}
        for side in ("away", "home"):
            team = game_teams.get(side)
            if not isinstance(team, dict) or not isinstance(team.get("name"), str):
                raise LiveFeedError(f"MLB feed is missing gameData.teams.{side}.name")
            teams[side] = {"id": team.get("id"), "name": team["name"]}
        return teams

    def _merge_boxscore_team(
        self,
        participants: dict[int, dict[str, Any]],
        team_data: Any,
        teams: dict[str, dict[str, Any]],
        side: str,
    ) -> None:
        if not isinstance(team_data, dict):
            return
        players = team_data.get("players")
        if not isinstance(players, dict):
            return
        for entry in players.values():
            if not isinstance(entry, dict):
                continue
            person = entry.get("person")
            if not isinstance(person, dict):
                continue
            player_id = person.get("id")
            name = person.get("fullName")
            if not isinstance(player_id, int) or not isinstance(name, str) or not name:
                continue
            roles = self._boxscore_roles(entry)
            if not roles:
                continue
            self._merge_participant(participants, player_id, name, teams, side, roles)

    def _boxscore_roles(self, entry: dict[str, Any]) -> set[WatchRole]:
        roles: set[WatchRole] = set()
        position = entry.get("position") if isinstance(entry.get("position"), dict) else {}
        position_type = position.get("type")
        position_code = str(position.get("code") or "")
        stats = entry.get("stats") if isinstance(entry.get("stats"), dict) else {}
        batting = stats.get("batting") if isinstance(stats.get("batting"), dict) else {}
        pitching = stats.get("pitching") if isinstance(stats.get("pitching"), dict) else {}
        if entry.get("battingOrder") or batting:
            roles.add(WatchRole.BATTER)
        if pitching or position_type == "Pitcher" or position_code == "1":
            roles.add(WatchRole.PITCHER)
        if not roles and position_type != "Pitcher":
            roles.add(WatchRole.BATTER)
        return roles

    def _merge_observed_play(
        self,
        participants: dict[int, dict[str, Any]],
        play: dict[str, Any],
        teams: dict[str, dict[str, Any]],
    ) -> None:
        about = play.get("about") if isinstance(play.get("about"), dict) else {}
        matchup = play.get("matchup") if isinstance(play.get("matchup"), dict) else {}
        top = about.get("isTopInning") is True
        batter_side = "away" if top else "home"
        pitcher_side = "home" if top else "away"
        batter = matchup.get("batter") if isinstance(matchup.get("batter"), dict) else {}
        pitcher = matchup.get("pitcher") if isinstance(matchup.get("pitcher"), dict) else {}
        self._merge_observed_player(
            participants, batter, teams, batter_side, WatchRole.BATTER
        )
        self._merge_observed_player(
            participants, pitcher, teams, pitcher_side, WatchRole.PITCHER
        )

    def _merge_observed_player(
        self,
        participants: dict[int, dict[str, Any]],
        player: dict[str, Any],
        teams: dict[str, dict[str, Any]],
        side: str,
        role: WatchRole,
    ) -> None:
        player_id = player.get("id")
        name = player.get("fullName")
        if not isinstance(player_id, int) or not isinstance(name, str) or not name:
            return
        self._merge_participant(participants, player_id, name, teams, side, {role})

    @staticmethod
    def _merge_participant(
        participants: dict[int, dict[str, Any]],
        player_id: int,
        name: str,
        teams: dict[str, dict[str, Any]],
        side: str,
        roles: set[WatchRole],
    ) -> None:
        team = teams[side]
        existing = participants.setdefault(
            player_id,
            {
                "name": name,
                "team_id": team.get("id"),
                "team_name": team["name"],
                "team_side": side,
                "roles": set(),
            },
        )
        existing["roles"].update(roles)

    @staticmethod
    def _terminal_pitch(play: dict[str, Any]) -> dict[str, Any] | None:
        events = play.get("playEvents")
        if not isinstance(events, list):
            return None
        for event in reversed(events):
            if isinstance(event, dict) and event.get("isPitch") is True:
                return event
        return None
