"""PregameContextBuilder: assembling usage, status, and limitations."""

from __future__ import annotations

from datetime import date

from app.pregame.context import PregameContextBuilder
from app.pregame.sample_size import SampleStatus
from app.pregame.sources.statcast import parse_csv_rows


def test_context_totals_and_overall_status(statcast_rows):
    records = parse_csv_rows(statcast_rows)

    context = PregameContextBuilder().build(
        pitcher_id=600001,
        start_date=date(2025, 8, 1),
        end_date=date(2025, 8, 15),
        records=records,
    )

    assert context.pitcher_id == 600001
    assert context.total_pitches == 30
    assert context.overall_status is SampleStatus.SUFFICIENT


def test_context_carries_both_usage_breakdowns(statcast_rows):
    records = parse_csv_rows(statcast_rows)

    context = PregameContextBuilder().build(
        pitcher_id=600001, start_date=date(2025, 8, 1), end_date=date(2025, 8, 15),
        records=records,
    )

    type_names = {row.pitch_type for row in context.pitch_usage_by_type}
    assert type_names == {"FF", "SL", "CH"}
    count_buckets = {(row.balls, row.strikes) for row in context.pitch_usage_by_count}
    assert count_buckets == {(0, 0), (1, 2)}


def test_low_sample_buckets_stay_in_the_context_but_are_flagged(statcast_rows):
    records = parse_csv_rows(statcast_rows)

    context = PregameContextBuilder().build(
        pitcher_id=600001, start_date=date(2025, 8, 1), end_date=date(2025, 8, 15),
        records=records,
    )

    by_type = {row.pitch_type: row for row in context.pitch_usage_by_type}
    assert by_type["FF"].status is SampleStatus.SUFFICIENT
    assert by_type["SL"].status is SampleStatus.INSUFFICIENT_SAMPLE
    assert by_type["CH"].status is SampleStatus.INSUFFICIENT_SAMPLE
    # Low-sample rows are not dropped from the structured context.
    assert "SL" in by_type
    assert "CH" in by_type


def test_limitations_call_out_every_insufficient_bucket(statcast_rows):
    records = parse_csv_rows(statcast_rows)

    context = PregameContextBuilder().build(
        pitcher_id=600001, start_date=date(2025, 8, 1), end_date=date(2025, 8, 15),
        records=records,
    )

    limitations_text = " ".join(context.limitations)
    assert "'SL'" in limitations_text
    assert "'CH'" in limitations_text
    assert "1-2 count" in limitations_text
    # The sufficient bucket is not flagged as a limitation.
    assert "'FF'" not in limitations_text
    assert "0-0 count" not in limitations_text


def test_empty_records_produce_a_no_data_limitation():
    context = PregameContextBuilder().build(
        pitcher_id=1, start_date=date(2025, 8, 1), end_date=date(2025, 8, 2), records=[]
    )

    assert context.total_pitches == 0
    assert context.overall_status is SampleStatus.INSUFFICIENT_SAMPLE
    assert any("No pitches were found" in note for note in context.limitations)
