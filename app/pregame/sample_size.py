"""The sample-size guard.

Applied per aggregation bucket, not to the pitcher's overall pitch count: a
pitcher can have thousands of tracked pitches while one rarely-thrown pitch
type still has only a handful of observations. Each bucket's own sample
size decides whether it may be described as a tendency.
"""

from __future__ import annotations

from enum import StrEnum

MIN_SAMPLE_SIZE = 20


class SampleStatus(StrEnum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT_SAMPLE = "insufficient_sample"


def evaluate(sample_size: int) -> SampleStatus:
    return (
        SampleStatus.SUFFICIENT
        if sample_size >= MIN_SAMPLE_SIZE
        else SampleStatus.INSUFFICIENT_SAMPLE
    )
