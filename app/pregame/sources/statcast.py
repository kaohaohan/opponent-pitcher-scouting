"""Statcast pitch-level source: Baseball Savant's public CSV search endpoint.

No pybaseball, no pandas: the endpoint returns CSV over plain HTTP, parsed
with the stdlib `csv` module. Row-to-`PitchRecord` normalization
(`parse_csv_rows`) is a pure function so tests exercise it directly against
fixture rows, with no network call and no live Statcast dependency.
"""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Iterable
from datetime import date

import httpx

from ..schemas import PitchRecord
from .base import PitchDataSource

logger = logging.getLogger(__name__)

STATCAST_SEARCH_URL = "https://baseballsavant.mlb.com/statcast_search/csv"
_REQUEST_TIMEOUT_SECONDS = 30.0


class StatcastFetchError(RuntimeError):
    """Raised when the Statcast source cannot be reached or parsed."""


class StatcastPitchSource(PitchDataSource):
    """Fetches one pitcher's tracked pitches from Baseball Savant."""

    name = "statcast"

    def fetch_pitcher_pitches(
        self, pitcher_id: int, start_date: date, end_date: date
    ) -> list[PitchRecord]:
        params = {
            "all": "true",
            "hfGT": "R|",
            "player_type": "pitcher",
            "pitchers_lookup[]": str(pitcher_id),
            "game_date_gt": start_date.isoformat(),
            "game_date_lt": end_date.isoformat(),
            "min_pitches": "0",
            "min_results": "0",
            "group_by": "name",
            "sort_col": "pitches",
            "player_event_sort": "api_p_release_speed",
            "sort_order": "desc",
            "min_pas": "0",
            "type": "details",
        }
        try:
            response = httpx.get(
                STATCAST_SEARCH_URL, params=params, timeout=_REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise StatcastFetchError(f"Could not fetch Statcast data: {exc}") from exc

        csv_text = response.content.decode("utf-8-sig")
        return parse_csv_rows(csv.DictReader(io.StringIO(csv_text)))


#: Statcast `pitch_type` codes that record a non-competitive throw rather
#: than a pitch in the pitcher's arsenal: pitchouts, intentional balls,
#: automatic (pitch-clock) balls, and unclassified pitches. Counting them
#: would put a "Pitchout 0.2%" row in the pitch mix and dilute every real
#: pitch type's usage share, so they're dropped here and in live metrics.
NON_ARSENAL_PITCH_TYPES: frozenset[str] = frozenset({"PO", "IN", "AB", "UN"})


def parse_csv_rows(rows: Iterable[dict[str, str]]) -> list[PitchRecord]:
    """Normalize raw Statcast CSV rows into `PitchRecord`s.

    A row with no `pitch_type` (e.g. a pickoff throw) carries no usable
    pitch identity and is skipped rather than guessed at, as is a
    non-arsenal throw (`NON_ARSENAL_PITCH_TYPES`). Any other row
    that fails validation is skipped and logged — one malformed row does
    not abort the fetch, matching Phase 1's handling of a single malformed
    event.
    """
    records: list[PitchRecord] = []
    for row in rows:
        pitch_type = (row.get("pitch_type") or "").strip()
        if not pitch_type or pitch_type.upper() in NON_ARSENAL_PITCH_TYPES:
            continue
        try:
            records.append(
                PitchRecord(
                    pitcher_id=row["pitcher"],
                    game_pk=row["game_pk"],
                    game_date=row["game_date"],
                    at_bat_number=row["at_bat_number"],
                    pitch_number=row["pitch_number"],
                    pitch_type=pitch_type,
                    balls=row["balls"],
                    strikes=row["strikes"],
                    release_speed=row.get("release_speed"),
                )
            )
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping malformed Statcast row: %s", exc)
    return records
