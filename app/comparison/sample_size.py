"""The live-comparison sample-size guard.

A live in-game pitch sample is structurally much smaller than the
multi-game Statcast window `app.pregame.sample_size` guards — reusing
that module's `MIN_SAMPLE_SIZE = 20` would mark almost every in-progress
outing as insufficient. These thresholds are sized for "how many pitches
has this pitcher thrown in the game so far", not "how many games of
Statcast history do we have".

Two independent guards:

- `MIN_LIVE_PITCHES_FOR_ANY_CLAIM` gates the *whole* comparison: below it,
  nothing is claimed as a trend yet, only "too early to tell".
- `MIN_PITCH_TYPE_SAMPLE` gates one pitch type's *own* row: a type thrown
  only once or twice can swing by double-digit percentage points on the
  next pitch alone, so its usage % is not yet meaningful even if the
  pitcher's overall pitch count clears the first guard.

`is_notable` further gates whether a *sufficient* row's delta is large
enough to be worth narrating at all — see `NOTABLE_USAGE_DELTA_PP` /
`NOTABLE_VELOCITY_DELTA_MPH` and `app.comparison.compare`.
"""

from __future__ import annotations

from app.pregame.sample_size import SampleStatus

#: Below this many total live pitches by the pitcher, the comparison as a
#: whole is too small a sample to draw any conclusion from. ~10 pitches is
#: roughly two to three batters faced — enough to have seen more than one
#: pitch-selection decision, not enough to be statistically meaningful.
MIN_LIVE_PITCHES_FOR_ANY_CLAIM = 10

#: Below this many live instances of one specific pitch type, that type's
#: own usage/velocity row is not yet meaningful on its own, even if the
#: pitcher's total pitch count clears `MIN_LIVE_PITCHES_FOR_ANY_CLAIM`.
MIN_PITCH_TYPE_SAMPLE = 5

#: A row's usage delta must clear this many percentage points to be
#: eligible for `is_notable`.
NOTABLE_USAGE_DELTA_PP = 10.0

#: A row's velocity delta must clear this many mph to be eligible for
#: `is_notable`.
NOTABLE_VELOCITY_DELTA_MPH = 1.5


def evaluate_overall(total_live_pitches: int) -> SampleStatus:
    """Sample status for the pitcher's live outing as a whole."""
    return (
        SampleStatus.SUFFICIENT
        if total_live_pitches >= MIN_LIVE_PITCHES_FOR_ANY_CLAIM
        else SampleStatus.INSUFFICIENT_SAMPLE
    )


def evaluate_pitch_type(live_sample_size: int) -> SampleStatus:
    """Sample status for one pitch type's own live count."""
    return (
        SampleStatus.SUFFICIENT
        if live_sample_size >= MIN_PITCH_TYPE_SAMPLE
        else SampleStatus.INSUFFICIENT_SAMPLE
    )
