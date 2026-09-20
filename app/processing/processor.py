"""The ingestion pipeline.

For each event from a source:

1. Receive the event.
2. Ignore it if the plate appearance is not complete.
3. Normalize and validate it into a `PlateAppearanceEvent`.
4. Insert it idempotently.
5. Evaluate the watch rules — but only for an event that was actually new.
6. Persist the generated alerts.

Step 5's condition is the whole point of doing step 4 with `ON CONFLICT DO
NOTHING RETURNING`: replaying the same game twice stores nothing the second time
and therefore raises no second round of alerts.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from .. import repository
from ..rules import RuleEngine, RuleMatch
from ..schemas import PlateAppearanceEvent, ReplayReport
from ..sources.base import PlateAppearanceSource, RawEvent

logger = logging.getLogger(__name__)


class ProcessOutcome(StrEnum):
    STORED = "stored"
    DUPLICATE = "duplicate"
    IGNORED_INCOMPLETE = "ignored_incomplete"
    INVALID = "invalid"


@dataclass(frozen=True)
class ProcessResult:
    outcome: ProcessOutcome
    plate_appearance_id: int | None = None
    alerts: tuple[RuleMatch, ...] = field(default_factory=tuple)
    error: str | None = None

    @property
    def stored(self) -> bool:
        return self.outcome is ProcessOutcome.STORED


class PlateAppearanceProcessor:
    """Turns source events into stored plate appearances and alerts."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        rule_engine: RuleEngine | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._rule_engine = rule_engine or RuleEngine()

    def process_event(self, raw_event: RawEvent) -> ProcessResult:
        """Run one event through the pipeline."""
        # Step 2 — an in-progress plate appearance is not news yet. Checked before
        # validation so a partial in-flight payload is never treated as malformed.
        if not raw_event.get("is_complete", False):
            return ProcessResult(outcome=ProcessOutcome.IGNORED_INCOMPLETE)

        # Step 3
        try:
            event = PlateAppearanceEvent.model_validate(dict(raw_event))
        except ValidationError as exc:
            logger.warning(
                "Discarding malformed plate-appearance event for game %r at-bat %r: %s",
                raw_event.get("game_id"),
                raw_event.get("at_bat_index"),
                exc,
            )
            return ProcessResult(outcome=ProcessOutcome.INVALID, error=str(exc))

        with self._session_factory() as session:
            result = self._persist(session, event)
            session.commit()
        return result

    def _persist(self, session: Session, event: PlateAppearanceEvent) -> ProcessResult:
        player = repository.get_or_create_player(session, event)

        # Step 4
        plate_appearance_id = repository.insert_plate_appearance(session, event, player.id)
        if plate_appearance_id is None:
            return ProcessResult(outcome=ProcessOutcome.DUPLICATE)

        # Steps 5 and 6
        matches = self._rule_engine.evaluate(event)
        repository.insert_alerts(session, plate_appearance_id, matches)
        return ProcessResult(
            outcome=ProcessOutcome.STORED,
            plate_appearance_id=plate_appearance_id,
            alerts=tuple(matches),
        )

    def process_source(self, source: PlateAppearanceSource) -> ReplayReport:
        """Drain a source sequentially and summarize what happened.

        A source that fails part-way through — a live feed losing its connection,
        a fixture that is not valid JSON — stops the drain but does not discard the
        events already ingested: each event commits in its own transaction, so the
        failure cannot roll back or corrupt earlier plate appearances. The error is
        logged and reported in `source_error` rather than swallowed.

        `NotImplementedError` is deliberately not caught: that is unimplemented
        code, not an upstream failure, and it should reach the caller.
        """
        results: list[ProcessResult] = []
        source_error: str | None = None

        try:
            events = iter(source.events())
        except NotImplementedError:
            raise
        except Exception as exc:
            logger.exception("Source %r could not be opened", source.name)
            return _summarize(source.name, results, _describe(exc))

        while True:
            try:
                raw_event = next(events)
            except StopIteration:
                break
            except NotImplementedError:
                raise
            except Exception as exc:
                logger.exception(
                    "Source %r failed after %d event(s); keeping what was ingested",
                    source.name,
                    len(results),
                )
                source_error = _describe(exc)
                break
            results.append(self.process_event(raw_event))

        return _summarize(source.name, results, source_error)


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _summarize(
    source_name: str,
    results: Sequence[ProcessResult],
    source_error: str | None = None,
) -> ReplayReport:
    def count(outcome: ProcessOutcome) -> int:
        return sum(1 for result in results if result.outcome is outcome)

    return ReplayReport(
        source=source_name,
        events_read=len(results),
        stored=count(ProcessOutcome.STORED),
        duplicates=count(ProcessOutcome.DUPLICATE),
        ignored_incomplete=count(ProcessOutcome.IGNORED_INCOMPLETE),
        invalid=count(ProcessOutcome.INVALID),
        alerts_created=sum(len(result.alerts) for result in results),
        source_error=source_error,
    )
