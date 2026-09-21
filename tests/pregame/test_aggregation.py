"""pitch_usage_by_type / pitch_usage_by_count: counts, percentages, and the
per-bucket sample size each one carries."""

from __future__ import annotations

from datetime import date

from app.pregame.aggregation import pitch_usage_by_count, pitch_usage_by_type
from app.pregame.sample_size import SampleStatus
from app.pregame.schemas import PitchRecord


def pitch(pitch_type: str, balls: int = 0, strikes: int = 0, **overrides) -> PitchRecord:
    defaults = dict(
        pitcher_id=1,
        game_pk=1,
        game_date=date(2025, 8, 10),
        at_bat_number=1,
        pitch_number=1,
        pitch_type=pitch_type,
        balls=balls,
        strikes=strikes,
        release_speed=95.0,
    )
    defaults.update(overrides)
    return PitchRecord(**defaults)


def test_pitch_usage_by_type_counts_and_percentages():
    records = [pitch("FF") for _ in range(3)] + [pitch("SL") for _ in range(1)]

    usage = pitch_usage_by_type(records)

    by_type = {row.pitch_type: row for row in usage}
    assert by_type["FF"].count == 3
    assert by_type["FF"].percentage == 75.0
    assert by_type["SL"].count == 1
    assert by_type["SL"].percentage == 25.0


def test_pitch_usage_by_type_sample_size_is_that_type_own_count():
    records = [pitch("FF") for _ in range(25)] + [pitch("SL") for _ in range(5)]

    usage = pitch_usage_by_type(records)

    by_type = {row.pitch_type: row for row in usage}
    assert by_type["FF"].sample_size == 25
    assert by_type["FF"].status is SampleStatus.SUFFICIENT
    assert by_type["SL"].sample_size == 5
    assert by_type["SL"].status is SampleStatus.INSUFFICIENT_SAMPLE


def test_pitch_usage_by_type_handles_no_records():
    assert pitch_usage_by_type([]) == []


def test_pitch_usage_by_count_groups_by_balls_and_strikes():
    records = (
        [pitch("FF", balls=0, strikes=0) for _ in range(3)]
        + [pitch("SL", balls=0, strikes=0) for _ in range(1)]
        + [pitch("CH", balls=1, strikes=2) for _ in range(2)]
    )

    usage = pitch_usage_by_count(records)
    buckets = {(row.balls, row.strikes, row.pitch_type): row for row in usage}

    assert buckets[(0, 0, "FF")].count == 3
    assert buckets[(0, 0, "FF")].percentage == 75.0
    assert buckets[(0, 0, "FF")].sample_size == 4  # denominator is the count's total
    assert buckets[(1, 2, "CH")].count == 2
    assert buckets[(1, 2, "CH")].percentage == 100.0
    assert buckets[(1, 2, "CH")].sample_size == 2


def test_pitch_usage_by_count_sample_size_is_the_count_total_not_the_pitch_type_total():
    # 25 pitches in the (0, 0) count are enough overall, even though only 3
    # of them are the SL within that count.
    records = [pitch("FF", 0, 0) for _ in range(22)] + [pitch("SL", 0, 0) for _ in range(3)]

    usage = pitch_usage_by_count(records)

    sl_row = next(row for row in usage if row.pitch_type == "SL")
    assert sl_row.sample_size == 25
    assert sl_row.status is SampleStatus.SUFFICIENT

    # But a count with too few total pitches is insufficient regardless of
    # how lopsided the pitch mix within it is.
    sparse = [pitch("FF", 2, 1) for _ in range(2)]
    sparse_usage = pitch_usage_by_count(sparse)
    assert sparse_usage[0].status is SampleStatus.INSUFFICIENT_SAMPLE
