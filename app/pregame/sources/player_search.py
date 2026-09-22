"""Pitcher name search: MLB Stats API's public people-search endpoint.

Same shape as `statcast.py` — a plain `httpx` GET against a public MLB
endpoint, with response parsing (`parse_people`) split out as a pure
function so tests exercise it against fixture payloads with no network call.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..schemas import PitcherSearchResult

logger = logging.getLogger(__name__)

MLB_PEOPLE_SEARCH_URL = "https://statsapi.mlb.com/api/v1/people/search"
_REQUEST_TIMEOUT_SECONDS = 10.0

#: MLB reports two-way players (e.g. Shohei Ohtani) under their own position
#: type rather than "Pitcher" — they still belong in a pitcher search.
_PITCHER_POSITION_TYPES = {"Pitcher", "Two-Way Player"}


class PitcherSearchError(RuntimeError):
    """Raised when the MLB people-search endpoint cannot be reached or parsed."""


class MLBPitcherSearchSource:
    """Looks up MLB pitchers by name via the public people-search endpoint."""

    name = "mlb_people_search"

    def search(self, query: str) -> list[PitcherSearchResult]:
        params = {"names": query, "sportId": "1", "hydrate": "currentTeam"}
        try:
            response = httpx.get(
                MLB_PEOPLE_SEARCH_URL, params=params, timeout=_REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PitcherSearchError(f"Could not search MLB pitchers: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise PitcherSearchError("MLB people search returned invalid JSON") from exc

        return parse_people(payload)


def parse_people(payload: Any) -> list[PitcherSearchResult]:
    """Filter a people-search payload down to pitchers, normalizing each row.

    A person missing an id or name is skipped rather than guessed at,
    matching how `statcast.parse_csv_rows` treats an unusable row.
    """
    people = payload.get("people") if isinstance(payload, dict) else None
    if not isinstance(people, list):
        return []

    results: list[PitcherSearchResult] = []
    for person in people:
        if not isinstance(person, dict):
            continue
        position = person.get("primaryPosition")
        position_type = position.get("type") if isinstance(position, dict) else None
        if position_type not in _PITCHER_POSITION_TYPES:
            continue
        player_id = person.get("id")
        name = person.get("fullName")
        if not isinstance(player_id, int) or not isinstance(name, str) or not name:
            logger.warning("Skipping malformed MLB people-search row: %r", person)
            continue

        current_team = person.get("currentTeam")
        team = (
            current_team.get("name")
            if isinstance(current_team, dict) and isinstance(current_team.get("name"), str)
            else None
        )
        pitch_hand = person.get("pitchHand")
        throws = (
            pitch_hand.get("code")
            if isinstance(pitch_hand, dict) and isinstance(pitch_hand.get("code"), str)
            else None
        )
        results.append(PitcherSearchResult(id=player_id, name=name, team=team, throws=throws))
    return results
