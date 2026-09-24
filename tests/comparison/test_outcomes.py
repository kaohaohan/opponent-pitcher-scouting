"""Deterministic outcome summaries from a live feed snapshot."""

from __future__ import annotations

from app.comparison.outcomes import compute_pitcher_outcome_context


def _play(
    pitcher_id: int,
    result: str,
    exit_velocity: float | None,
    *,
    complete: bool = True,
) -> dict:
    hit_data = {"launchSpeed": exit_velocity} if exit_velocity is not None else {}
    return {
        "about": {"isComplete": complete},
        "matchup": {"pitcher": {"id": pitcher_id}},
        "result": {"event": result},
        "playEvents": [{"isPitch": True, "hitData": hit_data}],
    }


def test_outcome_context_counts_completed_plays_and_known_exit_velocities():
    payload = {
        "liveData": {
            "plays": {
                "allPlays": [
                    _play(542881, "Home Run", 108.6),
                    _play(542881, "Double", 95.0),
                    _play(542881, "Single", None),
                    _play(542881, "Flyout", 99.9),
                    _play(542881, "Home Run", 120.0, complete=False),
                    _play(701002, "Home Run", 115.0),
                ]
            }
        }
    }

    context = compute_pitcher_outcome_context(payload, 542881)

    assert context.completed_plate_appearances == 4
    assert context.home_runs_allowed == 1
    assert context.extra_base_hits_allowed == 2
    assert context.hard_hit_contacts == 1
    assert context.hard_hit_threshold_mph == 100.0
    assert context.measured_exit_velocity_count == 3
    assert context.max_exit_velocity_mph == 108.6
    assert any("unavailable" in limitation for limitation in context.limitations)
