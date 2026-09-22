"""Source contract: sequential replay and live normalization."""

from __future__ import annotations

import json

import httpx
import pytest

from app.processing import ProcessOutcome
from app.schemas import PlateAppearanceEvent
from app.sources import LiveSource, PlateAppearanceSource, ReplaySource


def test_replay_source_yields_events_in_at_bat_order(fixture_path):
    events = list(ReplaySource(fixture_path).events())

    assert [event["at_bat_index"] for event in events] == [1, 2, 3, 4, 5, 6]


def test_replay_source_yields_events_out_of_fixture_order_sorted(tmp_path, fixture_path):
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["plate_appearances"].reverse()
    shuffled = tmp_path / "shuffled.json"
    shuffled.write_text(json.dumps(payload), encoding="utf-8")

    events = list(ReplaySource(shuffled).events())
    assert [event["at_bat_index"] for event in events] == [1, 2, 3, 4, 5, 6]


def test_replay_source_output_matches_the_normalized_contract(fixture_path):
    for raw in ReplaySource(fixture_path).events():
        event = PlateAppearanceEvent.model_validate(dict(raw))
        assert event.external_player_id == "mock-696285"
        assert event.player_name == "Hao-Yu Lee"
        assert event.game_id == "2025-08-14-WSH-PHI"


def test_replay_source_is_lazy_and_repeatable(fixture_path):
    source = ReplaySource(fixture_path)

    assert next(iter(source.events()))["at_bat_index"] == 1
    assert len(list(source.events())) == 6


def test_replay_source_from_default_fixture_points_at_a_real_file():
    assert ReplaySource.from_default_fixture().fixture_path.is_file()


def test_live_source_conforms_to_the_interface_and_surfaces_feed_errors():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    source = LiveSource(game_id=776743, watched_player_ids=("657557",), client=client)

    assert isinstance(source, PlateAppearanceSource)
    with pytest.raises(Exception, match="HTTP 503"):
        list(source.events())


def test_replaying_the_fixture_stores_five_plate_appearances_and_three_alerts(
    processor, fixture_path
):
    report = processor.process_source(ReplaySource(fixture_path))

    assert report.source == "replay"
    assert report.events_read == 6
    assert report.stored == 5
    assert report.ignored_incomplete == 1
    assert report.duplicates == 0
    assert report.invalid == 0
    # Double (extra-base hit + hard contact) and the single off a 97.3 mph fastball.
    assert report.alerts_created == 3


def test_replaying_the_fixture_twice_is_idempotent(processor, fixture_path):
    first = processor.process_source(ReplaySource(fixture_path))
    second = processor.process_source(ReplaySource(fixture_path))

    assert second.stored == 0
    assert second.duplicates == first.stored
    assert second.alerts_created == 0
    assert second.ignored_incomplete == 1


def test_processing_each_event_one_at_a_time_matches_a_full_replay(processor, fixture_path):
    outcomes = [
        processor.process_event(raw).outcome for raw in ReplaySource(fixture_path).events()
    ]

    assert outcomes.count(ProcessOutcome.STORED) == 5
    assert outcomes[-1] is ProcessOutcome.IGNORED_INCOMPLETE
