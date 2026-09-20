"""Pipeline behavior: what gets stored, what gets ignored, what stays NULL."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Alert, PlateAppearance, Player
from app.processing import ProcessOutcome
from tests.conftest import make_raw_event


def _count(session_factory: sessionmaker[Session], model) -> int:
    with session_factory() as session:
        return session.execute(select(func.count()).select_from(model)).scalar_one()


def test_completed_plate_appearance_is_processed(processor, session_factory):
    result = processor.process_event(make_raw_event())

    assert result.outcome is ProcessOutcome.STORED
    assert result.plate_appearance_id is not None
    assert _count(session_factory, PlateAppearance) == 1
    assert _count(session_factory, Player) == 1


def test_incomplete_plate_appearance_is_ignored(processor, session_factory):
    result = processor.process_event(
        make_raw_event(result="In Progress", is_complete=False)
    )

    assert result.outcome is ProcessOutcome.IGNORED_INCOMPLETE
    assert result.plate_appearance_id is None
    assert _count(session_factory, PlateAppearance) == 0
    # An ignored event must not even register the player.
    assert _count(session_factory, Player) == 0


def test_event_missing_is_complete_flag_is_ignored(processor, session_factory):
    raw = make_raw_event()
    del raw["is_complete"]

    assert processor.process_event(raw).outcome is ProcessOutcome.IGNORED_INCOMPLETE
    assert _count(session_factory, PlateAppearance) == 0


def test_duplicate_plate_appearance_is_not_duplicated(processor, session_factory):
    first = processor.process_event(make_raw_event(result="Double", exit_velocity=104.7))
    second = processor.process_event(make_raw_event(result="Double", exit_velocity=104.7))

    assert first.outcome is ProcessOutcome.STORED
    assert second.outcome is ProcessOutcome.DUPLICATE
    assert second.plate_appearance_id is None
    assert _count(session_factory, PlateAppearance) == 1
    # And crucially: no second round of alerts for the same plate appearance.
    assert second.alerts == ()
    assert _count(session_factory, Alert) == len(first.alerts)


def test_same_at_bat_index_in_a_different_game_is_a_new_plate_appearance(
    processor, session_factory
):
    processor.process_event(make_raw_event(game_id="game-a", at_bat_index=1))
    result = processor.process_event(make_raw_event(game_id="game-b", at_bat_index=1))

    assert result.outcome is ProcessOutcome.STORED
    assert _count(session_factory, PlateAppearance) == 2


def test_missing_statcast_fields_do_not_crash_and_stay_null(processor, session_factory):
    result = processor.process_event(
        make_raw_event(
            result="Flyout",
            pitch_type=None,
            pitch_velocity=None,
            exit_velocity=None,
            launch_angle=None,
        )
    )

    assert result.outcome is ProcessOutcome.STORED
    assert result.alerts == ()

    with session_factory() as session:
        stored = session.execute(select(PlateAppearance)).scalar_one()

    # Absent measurements must remain NULL, never 0.
    assert stored.pitch_type is None
    assert stored.pitch_velocity is None
    assert stored.exit_velocity is None
    assert stored.launch_angle is None


def test_omitted_statcast_keys_are_also_stored_as_null(processor, session_factory):
    raw = make_raw_event(result="Strikeout")
    for key in ("pitch_velocity", "exit_velocity", "launch_angle"):
        del raw[key]

    assert processor.process_event(raw).outcome is ProcessOutcome.STORED

    with session_factory() as session:
        stored = session.execute(select(PlateAppearance)).scalar_one()
    assert (stored.pitch_velocity, stored.exit_velocity, stored.launch_angle) == (
        None,
        None,
        None,
    )


def test_blank_statcast_strings_are_normalized_to_null(processor, session_factory):
    assert (
        processor.process_event(
            make_raw_event(exit_velocity="", pitch_velocity="  ", launch_angle="N/A")
        ).outcome
        is ProcessOutcome.STORED
    )

    with session_factory() as session:
        stored = session.execute(select(PlateAppearance)).scalar_one()
    assert (stored.pitch_velocity, stored.exit_velocity, stored.launch_angle) == (
        None,
        None,
        None,
    )


def test_malformed_event_is_rejected_without_raising(processor, session_factory):
    result = processor.process_event(make_raw_event(inning=0, result=""))

    assert result.outcome is ProcessOutcome.INVALID
    assert result.error
    assert _count(session_factory, PlateAppearance) == 0


def test_second_plate_appearance_reuses_the_existing_player(processor, session_factory):
    processor.process_event(make_raw_event(at_bat_index=1))
    processor.process_event(make_raw_event(at_bat_index=2, inning=3))

    assert _count(session_factory, Player) == 1
    assert _count(session_factory, PlateAppearance) == 2
