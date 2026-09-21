"""The sample-size guard's boundary at MIN_SAMPLE_SIZE."""

from __future__ import annotations

import pytest

from app.pregame.sample_size import MIN_SAMPLE_SIZE, SampleStatus, evaluate


def test_min_sample_size_is_twenty():
    assert MIN_SAMPLE_SIZE == 20


@pytest.mark.parametrize("sample_size", [20, 21, 100])
def test_at_or_above_the_threshold_is_sufficient(sample_size):
    assert evaluate(sample_size) is SampleStatus.SUFFICIENT


@pytest.mark.parametrize("sample_size", [0, 1, 19])
def test_below_the_threshold_is_insufficient(sample_size):
    assert evaluate(sample_size) is SampleStatus.INSUFFICIENT_SAMPLE
