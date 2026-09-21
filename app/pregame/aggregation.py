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
