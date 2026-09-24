"""compute_live_pitcher_metrics: pure aggregation from a raw MLB feed
snapshot, no network involved."""

from __future__ import annotations

import pytest

from app.comparison.live_metrics import compute_live_pitcher_metrics


def pitch_event(
    pitch_type: str | None,
    start_speed: float | None,
    *,
    as_code: bool = False,
) -> dict:
    event: dict = {"isPitch": True, "details": {}}
    if pitch_type is not None:
        key = "code" if as_code else "description"
        event["details"]["type"] = {key: pitch_type}
    if start_speed is not None:
        event["pitchData"] = {"startSpeed": start_speed}
    return event


def play(pitcher_id: int, pitcher_name: str, events: list[dict]) -> dict:
    return {
        "matchup": {"pitcher": {"id": pitcher_id, "fullName": pitcher_name}},
        "playEvents": events,
    }


def payload(plays: list[dict]) -> dict:
    return {"liveData": {"plays": {"allPlays": plays}}}


def test_counts_percentages_and_velocity_by_pitch_type():
    feed = payload(
        [
            play(
                542881,
                "Tyler Anderson",
                [
                    pitch_event("Four-Seam Fastball", 95.0),
                    pitch_event("Four-Seam Fastball", 97.0),
                    pitch_event("Slider", 87.5),
                ],
            )
        ]
    )

    metrics = compute_live_pitcher_metrics(feed, 542881)

    assert metrics.pitcher_id == 542881
    assert metrics.pitcher_name == "Tyler Anderson"
    assert metrics.total_pitches == 3
    by_type = {row.pitch_type: row for row in metrics.by_type}
    assert by_type["FF"].count == 2
    assert by_type["FF"].percentage == pytest.approx(66.7)
    assert by_type["FF"].avg_velocity == 96.0
    assert by_type["SL"].count == 1
    assert by_type["SL"].percentage == pytest.approx(33.3)
    assert by_type["SL"].avg_velocity == 87.5


def test_pitch_type_is_normalized_to_the_same_short_code_statcast_uses():
    """`app.pregame.sources.statcast` sources Statcast's `pitch_type`
    column (short codes like `SL`), but the MLB live feed's `description`
    is a full name (`Slider`) — a comparison row can only line up the two
    sides if they're normalized to the same vocabulary."""
    feed = payload([play(542881, "Tyler Anderson", [pitch_event("Slider", 87.5)])])

    metrics = compute_live_pitcher_metrics(feed, 542881)

    assert metrics.by_type[0].pitch_type == "SL"


def test_pitch_type_code_is_preferred_over_description_when_both_present():
    event = pitch_event("SL", 87.5, as_code=True)
    event["details"]["type"]["description"] = "Slider"
    feed = payload([play(542881, "Tyler Anderson", [event])])

    metrics = compute_live_pitcher_metrics(feed, 542881)

    assert metrics.by_type[0].pitch_type == "SL"


def test_unrecognized_description_falls_back_to_the_raw_string():
    feed = payload(
        [play(542881, "Tyler Anderson", [pitch_event("Some New Pitch Type", 90.0)])]
    )

    metrics = compute_live_pitcher_metrics(feed, 542881)

    assert metrics.by_type[0].pitch_type == "Some New Pitch Type"


def test_excludes_non_pitch_events_and_pickoffs():
    feed = payload(
        [
            play(
                542881,
                "Tyler Anderson",
                [
                    {"isPitch": False, "details": {"description": "mound visit"}},
                    pitch_event("Slider", 87.5),
                ],
            )
        ]
    )

    metrics = compute_live_pitcher_metrics(feed, 542881)

    assert metrics.total_pitches == 1
    assert metrics.by_type[0].pitch_type == "SL"


def test_excludes_pitches_thrown_by_a_different_pitcher():
    feed = payload(
        [
            play(542881, "Tyler Anderson", [pitch_event("Slider", 87.5)]),
            play(701002, "Two-Way Reserve", [pitch_event("Curveball", 78.0)]),
        ]
    )

    metrics = compute_live_pitcher_metrics(feed, 542881)

    assert metrics.total_pitches == 1
    assert metrics.by_type[0].pitch_type == "SL"


def test_pitcher_absent_from_feed_yields_zero_pitches_and_no_name():
    metrics = compute_live_pitcher_metrics(payload([]), 542881)

    assert metrics.pitcher_name is None
    assert metrics.total_pitches == 0
    assert metrics.by_type == []


def test_untyped_pitch_is_excluded_from_counts_and_denominator():
    feed = payload(
        [
            play(
                542881,
                "Tyler Anderson",
                [pitch_event(None, 95.0), pitch_event("Slider", 87.5)],
            )
        ]
    )

    metrics = compute_live_pitcher_metrics(feed, 542881)

    assert metrics.total_pitches == 1
    assert metrics.by_type[0].pitch_type == "SL"
    assert metrics.by_type[0].percentage == 100.0


def test_pitch_type_with_no_measured_velocity_averages_to_none():
    feed = payload([play(542881, "Tyler Anderson", [pitch_event("Slider", None)])])

    metrics = compute_live_pitcher_metrics(feed, 542881)

    assert metrics.by_type[0].avg_velocity is None


def test_includes_pitches_from_an_in_progress_at_bat():
    """Pitch-level events exist independent of `about.isComplete` — a
    batter mid at-bat has still seen real pitches, and Phase 5 counts them
    (per the approved plan, unlike Phase 1-4's completed-PA-only events)."""
    feed = payload(
        [
            {
                "about": {"isComplete": False},
                "matchup": {"pitcher": {"id": 542881, "fullName": "Tyler Anderson"}},
                "playEvents": [pitch_event("Slider", 87.5)],
            }
        ]
    )

    metrics = compute_live_pitcher_metrics(feed, 542881)

    assert metrics.total_pitches == 1


@pytest.mark.parametrize(
    ("pitch_type", "as_code"),
    [("PO", True), ("IN", True), ("Pitchout", False), ("Intentional Ball", False)],
)
def test_non_arsenal_throws_are_excluded_from_counts_and_denominator(pitch_type, as_code):
    feed = payload(
        [
            play(
                542881,
                "Tyler Anderson",
                [pitch_event(pitch_type, 80.0, as_code=as_code), pitch_event("Slider", 87.5)],
            )
        ]
    )

    metrics = compute_live_pitcher_metrics(feed, 542881)

    assert metrics.total_pitches == 1
    assert [row.pitch_type for row in metrics.by_type] == ["SL"]
