"""Shared fixtures for `tests/comparison/`."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.comparison.api import clear_baseline_cache, clear_comparison_note_cache


@pytest.fixture(autouse=True)
def _isolated_baseline_cache() -> Iterator[None]:
    """Clear the process-wide Statcast baseline cache before and after
    every test in this package, so one test's cached fetch can never leak
    into another's assertions about call counts or fetched data.
    """
    clear_baseline_cache()
    clear_comparison_note_cache()
    yield
    clear_baseline_cache()
    clear_comparison_note_cache()
