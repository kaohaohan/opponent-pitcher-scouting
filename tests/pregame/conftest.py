"""Shared fixtures for the Phase 2 test suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def statcast_rows() -> list[dict[str, Any]]:
    """Raw Statcast-shaped CSV rows: 30 valid pitches plus 1 pickoff to skip.

    Pitch types: FF=22 (sufficient), SL=5 (insufficient), CH=3 (insufficient).
    Counts: (0, 0) has 27 pitches (sufficient), (1, 2) has 3 (insufficient).
    One FF row has a blank release_speed to exercise null preservation.
    """
    payload = json.loads((FIXTURES_DIR / "statcast_sample.json").read_text(encoding="utf-8"))
    return payload["rows"]
