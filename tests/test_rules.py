"""Rule evaluation, including the absent-measurement cases."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Alert
from app.rules import RuleEngine, RuleType
from app.schemas import PlateAppearanceEvent
from tests.conftest import make_raw_event


def event(**overrides) -> PlateAppearanceEvent:
    return PlateAppearanceEvent.model_validate(make_raw_event(**overrides))


@pytest.fixture()
def engine() -> RuleEngine:
    return RuleEngine()


def rule_types(engine: RuleEngine, **overrides) -> set[RuleType]:
    return {match.rule_type for match in engine.evaluate(event(**overrides))}


@pytest.mark.parametrize("result", ["Double", "Triple", "Home Run"])
def test_extra_base_hit_fires(engine, result):
    assert RuleType.EXTRA_BASE_HIT in rule_types(engine, result=result)


@pytest.mark.parametrize("result", ["Single", "Groundout", "Strikeout", "Walk"])
def test_extra_base_hit_does_not_fire_for_other_results(engine, result):
    assert RuleType.EXTRA_BASE_HIT not in rule_types(engine, result=result)


@pytest.mark.parametrize("exit_velocity", [100.0, 104.7])
def test_hard_contact_fires_at_or_above_the_threshold(engine, exit_velocity):
    assert RuleType.HARD_CONTACT in rule_types(engine, exit_velocity=exit_velocity)


def test_hard_contact_does_not_fire_below_the_threshold(engine):
    assert RuleType.HARD_CONTACT not in rule_types(engine, exit_velocity=99.9)


def test_hard_contact_is_skipped_when_exit_velocity_is_missing(engine):
    assert rule_types(engine, result="Home Run", exit_velocity=None) == {
        RuleType.EXTRA_BASE_HIT
    }


@pytest.mark.parametrize("result", ["Single", "Double", "Triple", "Home Run"])
def test_high_velocity_hit_fires_for_hits_off_fast_pitches(engine, result):
    assert RuleType.HIGH_VELOCITY_HIT in rule_types(
        engine, result=result, pitch_velocity=95.0
    )


def test_high_velocity_hit_requires_a_hit(engine):
    assert RuleType.HIGH_VELOCITY_HIT not in rule_types(
        engine, result="Strikeout", pitch_velocity=99.1
    )


def test_high_velocity_hit_requires_a_fast_pitch(engine):
    assert RuleType.HIGH_VELOCITY_HIT not in rule_types(
        engine, result="Single", pitch_velocity=94.9
    )


def test_high_velocity_hit_is_skipped_when_pitch_velocity_is_missing(engine):
    assert rule_types(engine, result="Single", pitch_velocity=None) == set()


def test_a_single_plate_appearance_can_trigger_several_rules(engine):
    assert rule_types(
        engine, result="Home Run", exit_velocity=108.2, pitch_velocity=97.4
    ) == {
        RuleType.EXTRA_BASE_HIT,
        RuleType.HARD_CONTACT,
        RuleType.HIGH_VELOCITY_HIT,
    }


def test_no_rules_fire_for_an_ordinary_out(engine):
    assert rule_types(engine) == set()


def test_extra_base_hit_alert_is_persisted_with_its_rule_type(processor, session_factory):
    result = processor.process_event(
        make_raw_event(result="Double", exit_velocity=89.0, pitch_velocity=91.0)
    )

    assert [match.rule_type for match in result.alerts] == [RuleType.EXTRA_BASE_HIT]

    with session_factory() as session:
        alert = session.execute(select(Alert)).scalar_one()
    assert alert.rule_type == "extra_base_hit"
    assert alert.plate_appearance_id == result.plate_appearance_id
    assert "double" in alert.message.lower()
    assert alert.created_at is not None


def test_hard_contact_alert_is_persisted(processor, session_factory):
    result = processor.process_event(
        make_raw_event(result="Single", exit_velocity=101.3, pitch_velocity=90.0)
    )

    with session_factory() as session:
        rule_types_stored = set(session.execute(select(Alert.rule_type)).scalars())
    assert rule_types_stored == {"hard_contact"}
    assert len(result.alerts) == 1
