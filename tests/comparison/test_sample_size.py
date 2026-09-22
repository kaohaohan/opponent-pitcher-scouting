"""Boundary tests for the live-comparison sample-size thresholds."""

from __future__ import annotations

from app.comparison.sample_size import (
    MIN_LIVE_PITCHES_FOR_ANY_CLAIM,
    MIN_PITCH_TYPE_SAMPLE,
    evaluate_overall,
    evaluate_pitch_type,
)
from app.pregame.sample_size import SampleStatus


def test_evaluate_overall_is_insufficient_below_threshold():
    assert evaluate_overall(MIN_LIVE_PITCHES_FOR_ANY_CLAIM - 1) is SampleStatus.INSUFFICIENT_SAMPLE


def test_evaluate_overall_is_sufficient_at_threshold():
    assert evaluate_overall(MIN_LIVE_PITCHES_FOR_ANY_CLAIM) is SampleStatus.SUFFICIENT


def test_evaluate_pitch_type_is_insufficient_below_threshold():
    assert evaluate_pitch_type(MIN_PITCH_TYPE_SAMPLE - 1) is SampleStatus.INSUFFICIENT_SAMPLE


def test_evaluate_pitch_type_is_sufficient_at_threshold():
    assert evaluate_pitch_type(MIN_PITCH_TYPE_SAMPLE) is SampleStatus.SUFFICIENT
