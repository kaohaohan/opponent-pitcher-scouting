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

from ..schemas import PlateAppearanceEvent, WatchRole

HARD_CONTACT_EXIT_VELOCITY_MPH = 100.0
HIGH_PITCH_VELOCITY_MPH = 95.0


class RuleType(StrEnum):
    EXTRA_BASE_HIT = "extra_base_hit"
    HARD_CONTACT = "hard_contact"
    HIGH_VELOCITY_HIT = "high_velocity_hit"
    PITCHER_EXTRA_BASE_HIT_ALLOWED = "pitcher_extra_base_hit_allowed"
    PITCHER_HIGH_EXIT_VELOCITY_ALLOWED = "pitcher_high_exit_velocity_allowed"


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


def pitcher_extra_base_hit_allowed(event: PlateAppearanceEvent) -> RuleMatch | None:
    """Double, triple or home run allowed by the watched pitcher."""
    if not event.is_extra_base_hit:
        return None
    return RuleMatch(
        rule_type=RuleType.PITCHER_EXTRA_BASE_HIT_ALLOWED,
        message=(
            f"{event.pitcher_name} allowed a {event.result.lower()} "
            f"to {event.batter_name} (inning {event.inning})."
        ),
    )


def pitcher_high_exit_velocity_allowed(event: PlateAppearanceEvent) -> RuleMatch | None:
    """Exit velocity at or above 100 mph allowed by the watched pitcher."""
    if event.exit_velocity is None:
        return None
    if event.exit_velocity < HARD_CONTACT_EXIT_VELOCITY_MPH:
        return None
    return RuleMatch(
        rule_type=RuleType.PITCHER_HIGH_EXIT_VELOCITY_ALLOWED,
        message=(
            f"{event.pitcher_name} allowed hard contact: {event.exit_velocity:.1f} mph "
            f"exit velocity by {event.batter_name} (inning {event.inning})."
        ),
    )


#: Evaluation order is the order alerts are persisted in.
BATTER_RULES: tuple[Rule, ...] = (extra_base_hit, hard_contact, high_velocity_hit)
PITCHER_RULES: tuple[Rule, ...] = (
    pitcher_extra_base_hit_allowed,
    pitcher_high_exit_velocity_allowed,
)
RULES: tuple[Rule, ...] = BATTER_RULES


class RuleEngine:
    """Runs a set of rules against an event and collects the matches."""

    def __init__(
        self,
        rules: Sequence[Rule] | None = None,
        pitcher_rules: Sequence[Rule] | None = None,
    ) -> None:
        self.rules: tuple[Rule, ...] = tuple(rules) if rules is not None else BATTER_RULES
        self.pitcher_rules: tuple[Rule, ...] = (
            tuple(pitcher_rules) if pitcher_rules is not None else PITCHER_RULES
        )

    def evaluate(self, event: PlateAppearanceEvent) -> list[RuleMatch]:
        return self.evaluate_for_role(event, WatchRole.BATTER)

    def evaluate_for_role(
        self, event: PlateAppearanceEvent, role: WatchRole
    ) -> list[RuleMatch]:
        role = WatchRole(role)
        rules = self.pitcher_rules if role is WatchRole.PITCHER else self.rules
        matches = (rule(event) for rule in rules)
        return [match for match in matches if match is not None]
