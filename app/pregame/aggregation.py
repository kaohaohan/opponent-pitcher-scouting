"""Pitch-usage aggregation.

Pure functions from records to usage rows: counts, percentages and
per-bucket sample sizes, with no I/O and no LLM involved. This is where
"the backend calculates the baseball facts" happens.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence

from .sample_size import evaluate
from .schemas import PitchCountUsage, PitchRecord, PitchTypeUsage


def pitch_usage_by_type(records: Sequence[PitchRecord]) -> list[PitchTypeUsage]:
    """Usage of each pitch type across all records.

    A pitch type's `sample_size` is its own count, not the pitcher's total
    pitch count: a pitch thrown only a handful of times is low-sample
    regardless of how many pitches were tracked overall.
    """
    total = len(records)
    counts = Counter(record.pitch_type for record in records)

    usage = [
        PitchTypeUsage(
            pitch_type=pitch_type,
            count=count,
            percentage=round(count / total * 100, 1) if total else 0.0,
            sample_size=count,
            status=evaluate(count),
        )
        for pitch_type, count in counts.items()
    ]
    return sorted(usage, key=lambda row: (-row.count, row.pitch_type))


def pitch_usage_by_count(records: Sequence[PitchRecord]) -> list[PitchCountUsage]:
    """Usage of each pitch type within each ball-strike count.

    A row's `sample_size` is the total pitches thrown in that specific
    count, since that denominator is what makes its percentage meaningful
    (or not).
    """
    by_count: dict[tuple[int, int], Counter[str]] = defaultdict(Counter)
    for record in records:
        by_count[(record.balls, record.strikes)][record.pitch_type] += 1

    usage = []
    for (balls, strikes), counts in by_count.items():
        count_total = sum(counts.values())
        status = evaluate(count_total)
        for pitch_type, count in counts.items():
            usage.append(
                PitchCountUsage(
                    balls=balls,
                    strikes=strikes,
                    pitch_type=pitch_type,
                    count=count,
                    percentage=round(count / count_total * 100, 1),
                    sample_size=count_total,
                    status=status,
                )
            )
    return sorted(usage, key=lambda row: (row.balls, row.strikes, -row.count, row.pitch_type))


def avg_velocity_by_pitch_type(records: Sequence[PitchRecord]) -> dict[str, float | None]:
    """Average `release_speed` for each pitch type.

    A pitch type with every `release_speed` unmeasured maps to `None` (not
    `0.0`) — an absence of velocity data must never read as the softest
    pitch ever thrown. Velocity is averaged only over records that carry a
    measurement; a type with a mix of measured and unmeasured pitches still
    gets a real average from the ones that were tracked.
    """
    speeds_by_type: dict[str, list[float]] = defaultdict(list)
    types_seen: set[str] = set()
    for record in records:
        types_seen.add(record.pitch_type)
        if record.release_speed is not None:
            speeds_by_type[record.pitch_type].append(record.release_speed)

    def _average(pitch_type: str) -> float | None:
        speeds = speeds_by_type.get(pitch_type)
        return round(sum(speeds) / len(speeds), 1) if speeds else None

    return {pitch_type: _average(pitch_type) for pitch_type in types_seen}
