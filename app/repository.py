"""Persistence helpers. The only module that writes SQL.

Inserts use SQLite's `INSERT ... ON CONFLICT DO NOTHING RETURNING id` rather than
a SELECT-then-INSERT. Two reasons:

* Correctness — a check-then-insert has a race between the check and the insert.
  The unique index is the authority, so let the database arbitrate.
* It answers the only question the caller has in one round trip: RETURNING yields
  a row when this insert created the plate appearance, and no row when the plate
  appearance was already there. That distinction is what tells the processor
  whether to evaluate rules, so duplicate events cannot produce duplicate alerts.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .models import Alert, PlateAppearance, Player
from .rules import RuleMatch
from .schemas import PlateAppearanceEvent


def get_or_create_player(session: Session, event: PlateAppearanceEvent) -> Player:
    """Return the watched player for this event, inserting it if unseen.

    Idempotent on `external_player_id` via the same conflict-handling approach.
    """
    stmt = (
        sqlite_insert(Player)
        .values(
            external_player_id=event.external_player_id,
            name=event.player_name,
            team=event.team,
        )
        .on_conflict_do_nothing(index_elements=["external_player_id"])
    )
    session.execute(stmt)
    return session.execute(
        select(Player).where(Player.external_player_id == event.external_player_id)
    ).scalar_one()


def insert_plate_appearance(
    session: Session, event: PlateAppearanceEvent, player_id: int
) -> int | None:
    """Insert a plate appearance idempotently.

    Returns the new row's id, or `None` if `(game_id, at_bat_index)` already
    existed — in which case nothing was written.
    """
    stmt = (
        sqlite_insert(PlateAppearance)
        .values(
            game_id=event.game_id,
            player_id=player_id,
            at_bat_index=event.at_bat_index,
            inning=event.inning,
            result=event.result,
            pitcher=event.pitcher,
            # None stays None: absent measurements must not become 0.
            pitch_type=event.pitch_type,
            pitch_velocity=event.pitch_velocity,
            exit_velocity=event.exit_velocity,
            launch_angle=event.launch_angle,
            is_complete=event.is_complete,
        )
        .on_conflict_do_nothing(index_elements=["game_id", "at_bat_index"])
        .returning(PlateAppearance.id)
    )
    return session.execute(stmt).scalar_one_or_none()


def insert_alerts(
    session: Session, plate_appearance_id: int, matches: Sequence[RuleMatch]
) -> list[Alert]:
    """Persist the alerts for one plate appearance."""
    alerts = [
        Alert(
            plate_appearance_id=plate_appearance_id,
            rule_type=str(match.rule_type),
            message=match.message,
        )
        for match in matches
    ]
    session.add_all(alerts)
    return alerts


def list_players(session: Session) -> Sequence[Player]:
    return session.execute(select(Player).order_by(Player.id)).scalars().all()


def list_plate_appearances(
    session: Session,
    game_id: str | None = None,
    player_id: int | None = None,
    limit: int = 200,
) -> Sequence[PlateAppearance]:
    stmt = select(PlateAppearance)
    if game_id is not None:
        stmt = stmt.where(PlateAppearance.game_id == game_id)
    if player_id is not None:
        stmt = stmt.where(PlateAppearance.player_id == player_id)
    stmt = stmt.order_by(PlateAppearance.game_id, PlateAppearance.at_bat_index).limit(limit)
    return session.execute(stmt).scalars().all()


def list_alerts(
    session: Session, rule_type: str | None = None, limit: int = 200
) -> Sequence[Alert]:
    stmt = select(Alert)
    if rule_type is not None:
        stmt = stmt.where(Alert.rule_type == rule_type)
    stmt = stmt.order_by(Alert.id.desc()).limit(limit)
    return session.execute(stmt).scalars().all()
