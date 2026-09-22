"""Failure handling: failures are logged and reported, never silently hidden,
and a source that dies part-way through must not corrupt what it already stored.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import func, select

from app.models import PlateAppearance
from app.processing import ProcessOutcome
from app.sources import LiveFeedError, LiveSource, PlateAppearanceSource, ReplaySource
from app.sources.base import RawEvent
from tests.conftest import make_raw_event


class FeedUnavailable(RuntimeError):
    """Stands in for whatever a real MLB client raises when the feed is down."""


class FlakySource(PlateAppearanceSource):
    """Yields `emit` events, then fails the way an external feed would."""

    name = "flaky"

    def __init__(self, emit: int) -> None:
        self.emit = emit

    def events(self) -> Iterator[RawEvent]:
        for at_bat_index in range(1, self.emit + 1):
            yield make_raw_event(at_bat_index=at_bat_index, inning=at_bat_index)
        raise FeedUnavailable("upstream returned 503")


class UnopenableSource(PlateAppearanceSource):
    """Fails before yielding anything — `events()` is not even a generator."""

    name = "unopenable"

    def events(self) -> Iterator[RawEvent]:
        raise FeedUnavailable("connection refused")


def _stored_count(session_factory) -> int:
    with session_factory() as session:
        return session.execute(
            select(func.count()).select_from(PlateAppearance)
        ).scalar_one()


def test_mid_stream_source_failure_keeps_already_ingested_events(
    processor, session_factory
):
    report = processor.process_source(FlakySource(emit=3))

    # The three events that arrived before the failure are committed and counted.
    assert report.stored == 3
    assert report.events_read == 3
    assert _stored_count(session_factory) == 3
    # And the failure is reported rather than swallowed.
    assert report.source_error is not None
    assert "FeedUnavailable" in report.source_error
    assert "503" in report.source_error


def test_mid_stream_source_failure_is_logged(processor, caplog):
    with caplog.at_level(logging.ERROR, logger="app.processing.processor"):
        processor.process_source(FlakySource(emit=2))

    assert any("failed after 2 event(s)" in record.message for record in caplog.records)


def test_source_that_cannot_be_opened_is_reported_not_raised(processor, session_factory):
    report = processor.process_source(UnopenableSource())

    assert report.events_read == 0
    assert report.stored == 0
    assert report.source_error is not None
    assert "connection refused" in report.source_error
    assert _stored_count(session_factory) == 0


def test_a_successful_replay_reports_no_source_error(processor, fixture_path):
    assert processor.process_source(ReplaySource(fixture_path)).source_error is None


def test_live_feed_error_can_be_propagated_for_http_translation(
    processor,
):
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    source = LiveSource(game_id=776743, watched_player_ids=("657557",), client=client)
    with pytest.raises(LiveFeedError):
        processor.process_source(source, propagate_source_errors=True)


def test_malformed_fixture_is_reported_as_a_source_error(processor, tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    report = processor.process_source(ReplaySource(broken))

    assert report.events_read == 0
    assert report.source_error is not None
    assert "JSONDecodeError" in report.source_error


def test_a_malformed_event_does_not_stop_the_rest_of_the_source(
    processor, tmp_path, fixture_path
):
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["plate_appearances"][0]["inning"] = 0  # fails validation
    damaged = tmp_path / "damaged.json"
    damaged.write_text(json.dumps(payload), encoding="utf-8")

    report = processor.process_source(ReplaySource(damaged))

    assert report.invalid == 1
    assert report.stored == 4
    assert report.ignored_incomplete == 1
    assert report.source_error is None


def test_invalid_event_is_logged_with_its_identifiers(processor, caplog):
    with caplog.at_level(logging.WARNING, logger="app.processing.processor"):
        result = processor.process_event(make_raw_event(game_id="game-x", inning=0))

    assert result.outcome is ProcessOutcome.INVALID
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "game-x" in logged
    assert "inning" in logged
