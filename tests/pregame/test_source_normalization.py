"""Statcast row normalization: types, skipping, and null preservation."""

from __future__ import annotations

from datetime import date

from app.pregame.sources.statcast import parse_csv_rows


def test_pickoff_rows_without_a_pitch_type_are_skipped(statcast_rows):
    records = parse_csv_rows(statcast_rows)

    assert len(records) == 30
    assert all(record.pitch_type for record in records)


def test_rows_are_normalized_into_typed_pitch_records(statcast_rows):
    records = parse_csv_rows(statcast_rows)
    first = records[0]

    assert first.pitcher_id == 600001
    assert first.game_pk == 700001
    assert first.game_date == date(2025, 8, 10)
    assert isinstance(first.at_bat_number, int)
    assert isinstance(first.pitch_number, int)
    assert isinstance(first.balls, int)
    assert isinstance(first.strikes, int)


def test_missing_release_speed_stays_null_not_zero(statcast_rows):
    records = parse_csv_rows(statcast_rows)

    blank_speed_records = [r for r in records if r.release_speed is None]
    assert len(blank_speed_records) == 1
    assert blank_speed_records[0].pitch_type == "FF"


def test_measured_release_speed_is_preserved(statcast_rows):
    records = parse_csv_rows(statcast_rows)

    measured = next(r for r in records if r.pitch_type == "SL")
    assert measured.release_speed == 85.2
