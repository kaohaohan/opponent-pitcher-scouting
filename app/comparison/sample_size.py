"""The live-comparison sample-size guard.

A live in-game pitch sample is structurally much smaller than the
multi-game Statcast window `app.pregame.sample_size` guards — reusing
that module's `MIN_SAMPLE_SIZE = 20` would mark almost every in-progress
outing as insufficient. These thresholds are sized for "how many pitches
has this pitcher thrown in the game so far", not "how many games of
Statcast history do we have".

Two independent guards on each row's own confidence:

- `MIN_LIVE_PITCHES_FOR_ANY_CLAIM` gates the *whole* comparison: below it,
  nothing is claimed as a trend yet, only "too early to tell".
- `MIN_PITCH_TYPE_SAMPLE` gates one pitch type's *own* row: a type thrown
  only once or twice can swing by double-digit percentage points on the
  next pitch alone, so its usage % is not yet meaningful even if the
  pitcher's overall pitch count clears the first guard.

The `USAGE_*`/`VELOCITY_*` constants below feed `app.comparison.signals`
instead — a separate, coarser layer that decides whether a gap is worth
flagging to a user at all ("watch" or "alert"), on top of (not instead of)
the two guards above.

IMPORTANT — every threshold in this module, including the usage and
velocity signal thresholds, is a **product heuristic** for "is this
worth a look", not a statistical significance test. None of them
corresponds to a p-value or a confidence interval, and clearing one is
never a claim about *why* a number moved — only that it moved enough,
with enough pitches behind it, to be worth a human glancing at it.
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

# --- Usage signal thresholds (app.comparison.signals) -----------------
#
# Denominator is each side's TOTAL pitch count (every pitch type
# combined), not this one pitch type's own count — a pitcher who has
# thrown 0 of 12 live pitches as a slider is a meaningful "hasn't gone to
# it yet" signal even though the slider's own live count is 0.

#: Below this many total baseline pitches, the baseline mix itself is too
#: thin to say a live pitch type's share has moved *from* it.
MIN_BASELINE_TOTAL_FOR_USAGE_SIGNAL = 100

#: Below this many total live pitches, a usage signal is never raised —
#: matches `MIN_LIVE_PITCHES_FOR_ANY_CLAIM`.
USAGE_WATCH_MIN_LIVE_TOTAL = MIN_LIVE_PITCHES_FOR_ANY_CLAIM

#: A usage signal reaches "alert" only once this many total live pitches
#: have been thrown, on top of clearing `USAGE_ALERT_DELTA_PP`.
USAGE_ALERT_MIN_LIVE_TOTAL = 30

#: Minimum |delta|, in percentage points, for a "watch"-level usage signal.
USAGE_WATCH_DELTA_PP = 8.0

#: Minimum |delta|, in percentage points, for an "alert"-level usage signal.
USAGE_ALERT_DELTA_PP = 10.0

# --- Velocity signal thresholds (app.comparison.signals) ---------------
#
# Denominator here is this ONE pitch type's own count on each side — a
# velocity comparison only makes sense for pitches of the same type.

#: Below this many baseline pitches of this type (with a measured
#: velocity), a velocity signal is never raised for it.
MIN_BASELINE_VELOCITY_SAMPLE = 20

#: Below this many *live* pitches of this type, a velocity signal is
#: never raised for it.
VELOCITY_WATCH_MIN_LIVE_COUNT = 3

#: A velocity signal reaches "alert" only once this many live pitches of
#: this type have been thrown, on top of clearing `VELOCITY_ALERT_DELTA_MPH`.
VELOCITY_ALERT_MIN_LIVE_COUNT = 8

#: Minimum |delta|, in mph, for a "watch"-level velocity signal.
VELOCITY_WATCH_DELTA_MPH = 1.0

#: Minimum |delta|, in mph, for an "alert"-level velocity signal.
VELOCITY_ALERT_DELTA_MPH = 1.5


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
