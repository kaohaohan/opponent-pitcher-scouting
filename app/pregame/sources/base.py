"""The pitch-data source interface.

Mirrors `app.sources.base.PlateAppearanceSource`: feed-specific concerns
(HTTP, pagination, a provider's column names) stay behind this boundary, so
swapping the data source later means writing one new class. Unlike Phase 1
sources — which yield raw mappings for a separate processor to validate —
`fetch_pitcher_pitches` returns validated `PitchRecord`s directly, since
Phase 2 has no separate ingestion pipeline: normalization happens at the
source boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from ..schemas import PitchRecord


class PitchDataSource(ABC):
    #: Short identifier, used in logs and error messages.
    name: str = "pitch_source"

    @abstractmethod
    def fetch_pitcher_pitches(
        self, pitcher_id: int, start_date: date, end_date: date
    ) -> list[PitchRecord]:
        """Fetch and normalize one pitcher's pitches in [start_date, end_date]."""
