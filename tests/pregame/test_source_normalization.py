"""Statcast row normalization: types, skipping, and null preservation."""

from __future__ import annotations

import csv
import io
from datetime import date

import httpx

from app.pregame.sources.statcast import StatcastPitchSource, parse_csv_rows

BOM_PREFIXED_CSV = (
    b'\xef\xbb\xbf"pitch_type",game_date,release_speed,pitcher,game_pk,'
    b"at_bat_number,pitch_number,balls,strikes\n"
    b"SL,2024-08-10,88.3,543037,745708,43,3,1,2\n"
    b",2024-08-10,82.9,543037,745708,43,2,1,1\n"
)


def test_pickoff_rows_without_a_pitch_type_are_skipped(statcast_rows):
    records = parse_csv_rows(statcast_rows)

    assert len(records) == 30
    assert all(record.pitch_type for record in records)


def test_blank_pitch_type_rows_are_still_skipped():
    rows = [
        {
            "pitch_type": "",
            "pitcher": "543037",
            "game_pk": "745708",
            "game_date": "2024-08-10",
            "at_bat_number": "43",
            "pitch_number": "2",
            "balls": "1",
            "strikes": "1",
            "release_speed": "82.9",
        }
    ]

    assert parse_csv_rows(rows) == []


def test_bom_prefixed_csv_header_parses_correctly():
    csv_text = BOM_PREFIXED_CSV.decode("utf-8-sig")
    rows = csv.DictReader(io.StringIO(csv_text))
    records = parse_csv_rows(rows)

    assert len(records) == 1
    assert records[0].pitch_type == "SL"
    assert records[0].pitcher_id == 543037


def test_fetch_pitcher_pitches_handles_bom_prefixed_savant_content(monkeypatch):
    def fake_get(url, params, timeout):
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(200, content=BOM_PREFIXED_CSV, request=request)

    monkeypatch.setattr(httpx, "get", fake_get)

    records = StatcastPitchSource().fetch_pitcher_pitches(
        pitcher_id=543037,
        start_date=date(2024, 8, 10),
        end_date=date(2024, 8, 11),
    )

    assert len(records) == 1
    assert records[0].pitch_type == "SL"
    assert records[0].release_speed == 88.3


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
