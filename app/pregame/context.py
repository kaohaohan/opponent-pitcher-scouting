"""Builds the structured `PregameContext` that is the only thing an
`LLMProvider` receives. Nothing here writes prose — that is Gemini's job.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from .aggregation import avg_velocity_by_pitch_type, pitch_usage_by_count, pitch_usage_by_type
from .sample_size import SampleStatus, evaluate
from .schemas import PitchRecord, PregameContext


class PregameContextBuilder:
    """Assembles a `PregameContext` from raw pitch records."""

    def build(
        self,
        pitcher_id: int,
        start_date: date,
        end_date: date,
        records: Sequence[PitchRecord],
    ) -> PregameContext:
        by_type = pitch_usage_by_type(records)
        velocities = avg_velocity_by_pitch_type(records)
        for row in by_type:
            row.avg_velocity = velocities.get(row.pitch_type)
        by_count = pitch_usage_by_count(records)
        total = len(records)

        limitations = [
            f"Only {row.sample_size} pitch(es) of type {row.pitch_type!r} were "
            "observed in this window; its usage share is not a meaningful tendency."
            for row in by_type
            if row.status is SampleStatus.INSUFFICIENT_SAMPLE
        ]
        insufficient_counts = {
            (row.balls, row.strikes): row.sample_size
            for row in by_count
            if row.status is SampleStatus.INSUFFICIENT_SAMPLE
        }
        limitations.extend(
            f"Only {sample_size} pitch(es) were observed in the {balls}-{strikes} "
            "count; usage shares there are not meaningful tendencies."
            for (balls, strikes), sample_size in sorted(insufficient_counts.items())
        )
        if total == 0:
            limitations.append(
                "No pitches were found for this pitcher in the given date window."
            )

        return PregameContext(
            pitcher_id=pitcher_id,
            start_date=start_date,
            end_date=end_date,
            total_pitches=total,
            pitch_usage_by_type=by_type,
            pitch_usage_by_count=by_count,
            overall_status=evaluate(total),
            limitations=limitations,
        )
