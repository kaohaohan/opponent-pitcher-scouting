"""Watch rules and the engine that evaluates them.

Every rule is a pure function from a normalized event to an optional `RuleMatch`.
No database, no session, no I/O — which is what makes the rules cheap to test and
safe to reorder.

Missing Statcast data is the default case, not an error case: a rule that depends
on a measurement returns `None` when that measurement is absent. Comparisons are
never made against a substituted zero.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from ..schemas import PlateAppearanceEvent

HARD_CONTACT_EXIT_VELOCITY_MPH = 100.0
HIGH_PITCH_VELOCITY_MPH = 95.0


class RuleType(StrEnum):
    EXTRA_BASE_HIT = "extra_base_hit"
    HARD_CONTACT = "hard_contact"
    HIGH_VELOCITY_HIT = "high_velocity_hit"


@dataclass(frozen=True)
class RuleMatch:
    """A rule that fired, plus the human-readable text for its alert."""

    rule_type: RuleType
    message: str


Rule = Callable[[PlateAppearanceEvent], RuleMatch | None]


def extra_base_hit(event: PlateAppearanceEvent) -> RuleMatch | None:
    """Double, triple or home run."""
    if not event.is_extra_base_hit:
        return None
    return RuleMatch(
        rule_type=RuleType.EXTRA_BASE_HIT,
        message=(
            f"{event.player_name} hit a {event.result.lower()} "
            f"off {event.pitcher} (inning {event.inning})."
        ),
    )


def hard_contact(event: PlateAppearanceEvent) -> RuleMatch | None:
    """Exit velocity at or above 100 mph. Skipped when exit velocity is missing."""
    if event.exit_velocity is None:
        return None
    if event.exit_velocity < HARD_CONTACT_EXIT_VELOCITY_MPH:
        return None
    return RuleMatch(
        rule_type=RuleType.HARD_CONTACT,
        message=(
            f"{event.player_name} made hard contact: {event.exit_velocity:.1f} mph "
            f"exit velocity on a {event.result.lower()} (inning {event.inning})."
        ),
    )


def high_velocity_hit(event: PlateAppearanceEvent) -> RuleMatch | None:
    """A hit against a pitch of 95 mph or more. Skipped when pitch velocity is missing."""
    if event.pitch_velocity is None:
        return None
    if event.pitch_velocity < HIGH_PITCH_VELOCITY_MPH or not event.is_hit:
        return None
    pitch = event.pitch_type or "pitch"
    return RuleMatch(
        rule_type=RuleType.HIGH_VELOCITY_HIT,
        message=(
            f"{event.player_name} got a {event.result.lower()} off a "
            f"{event.pitch_velocity:.1f} mph {pitch.lower()} from {event.pitcher} "
            f"(inning {event.inning})."
        ),
    )


#: Evaluation order is the order alerts are persisted in.
RULES: tuple[Rule, ...] = (extra_base_hit, hard_contact, high_velocity_hit)


class RuleEngine:
    """Runs a set of rules against an event and collects the matches."""

    def __init__(self, rules: Sequence[Rule] | None = None) -> None:
        self.rules: tuple[Rule, ...] = tuple(rules) if rules is not None else RULES

    def evaluate(self, event: PlateAppearanceEvent) -> list[RuleMatch]:
        matches = (rule(event) for rule in self.rules)
        return [match for match in matches if match is not None]
