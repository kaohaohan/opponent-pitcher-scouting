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
from datetime import UTC, datetime

from sqlalchemy import distinct, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .comparison.schemas import Signal
from .models import Alert, PitchMixAlert, PlateAppearance, Player
from .rules import RuleMatch
from .schemas import PlateAppearanceEvent, WatchRole


def get_or_create_player(
    session: Session, external_player_id: str, name: str, team: str | None
) -> Player:
    """Return a player identity, inserting it if unseen.

    Idempotent on `external_player_id` via the same conflict-handling approach.
    """
    stmt = (
        sqlite_insert(Player)
        .values(
            external_player_id=external_player_id,
            name=name,
            team=team or "—",
        )
        .on_conflict_do_nothing(index_elements=["external_player_id"])
    )
    session.execute(stmt)
    return session.execute(
        select(Player).where(Player.external_player_id == external_player_id)
    ).scalar_one()


def insert_plate_appearance(
    session: Session,
    event: PlateAppearanceEvent,
    batter_player_id: int,
    pitcher_player_id: int | None = None,
) -> int | None:
    """Insert a plate appearance idempotently.

    Returns the new row's id, or `None` if `(game_id, at_bat_index)` already
    existed — in which case nothing was written.
    """
    stmt = (
        sqlite_insert(PlateAppearance.__table__)
        .values(
            game_id=event.game_id,
            player_id=batter_player_id,
            pitcher_player_id=pitcher_player_id,
            at_bat_index=event.at_bat_index,
            inning=event.inning,
            result=event.result,
            pitcher=event.pitcher_name,
            # None stays None: absent measurements must not become 0.
            pitch_type=event.pitch_type,
            pitch_velocity=event.pitch_velocity,
            exit_velocity=event.exit_velocity,
            launch_angle=event.launch_angle,
            is_complete=event.is_complete,
        )
        .on_conflict_do_nothing(index_elements=["game_id", "at_bat_index"])
        .returning(PlateAppearance.__table__.c.id)
    )
    return session.execute(stmt).scalar_one_or_none()


def get_plate_appearance_id(
    session: Session, game_id: str, at_bat_index: int
) -> int | None:
    return session.execute(
        select(PlateAppearance.id).where(
            PlateAppearance.game_id == game_id,
            PlateAppearance.at_bat_index == at_bat_index,
        )
    ).scalar_one_or_none()


def fill_missing_pitcher_player(
    session: Session, plate_appearance_id: int, pitcher_player_id: int | None
) -> None:
    if pitcher_player_id is None:
        return
    plate_appearance = session.get(PlateAppearance, plate_appearance_id)
    if plate_appearance is not None and plate_appearance.pitcher_player_id is None:
        plate_appearance.pitcher_player_id = pitcher_player_id


def insert_alerts(
    session: Session,
    plate_appearance_id: int,
    subject_role: WatchRole,
    matches: Sequence[RuleMatch],
) -> list[Alert]:
    """Persist alerts for one plate appearance, role, and rule idempotently."""
    alerts: list[Alert] = []
    for match in matches:
        stmt = (
            sqlite_insert(Alert)
            .values(
                plate_appearance_id=plate_appearance_id,
                subject_role=str(subject_role),
                rule_type=str(match.rule_type),
                message=match.message,
            )
            .on_conflict_do_nothing(
                index_elements=["plate_appearance_id", "subject_role", "rule_type"]
            )
            .returning(Alert.id)
        )
        alert_id = session.execute(stmt).scalar_one_or_none()
        if alert_id is not None:
            alert = session.get(Alert, alert_id)
            if alert is not None:
                alerts.append(alert)
    return alerts


def list_players(session: Session) -> Sequence[Player]:
    player_ids = select(distinct(PlateAppearance.batter_player_id))
    return (
        session.execute(select(Player).where(Player.id.in_(player_ids)).order_by(Player.id))
        .scalars()
        .all()
    )


def list_plate_appearances(
    session: Session,
    game_id: str | None = None,
    player_id: int | None = None,
    batter_id: str | None = None,
    pitcher_id: str | None = None,
    limit: int = 200,
) -> Sequence[PlateAppearance]:
    stmt = select(PlateAppearance)
    if game_id is not None:
        stmt = stmt.where(PlateAppearance.game_id == game_id)
    if player_id is not None:
        stmt = stmt.where(PlateAppearance.batter_player_id == player_id)
    if batter_id is not None:
        stmt = stmt.join(PlateAppearance.batter).where(Player.external_player_id == batter_id)
    if pitcher_id is not None:
        pitcher = Player.__table__.alias("pitcher")
        stmt = stmt.join(pitcher, PlateAppearance.pitcher_player_id == pitcher.c.id).where(
            pitcher.c.external_player_id == pitcher_id
        )
    stmt = stmt.order_by(PlateAppearance.game_id, PlateAppearance.at_bat_index).limit(limit)
    return session.execute(stmt).scalars().all()


def list_alerts(
    session: Session,
    rule_type: str | None = None,
    subject_role: WatchRole | None = None,
    limit: int = 200,
) -> Sequence[Alert]:
    stmt = select(Alert)
    if rule_type is not None:
        stmt = stmt.where(Alert.rule_type == rule_type)
    if subject_role is not None:
        stmt = stmt.where(Alert.subject_role == str(subject_role))
    stmt = stmt.order_by(Alert.id.desc()).limit(limit)
    return session.execute(stmt).scalars().all()


def upsert_pitch_mix_signals(
    session: Session,
    *,
    game_id: str,
    pitcher_id: int,
    pitcher_name: str,
    team_name: str | None,
    signals: Sequence[Signal],
    live_total_pitches: int,
) -> list[PitchMixAlert]:
    """Upsert one pitcher's pitch-mix signals for this sync's evaluation.

    Rules (see `app.models.PitchMixAlert`):
    * A `(metric, pitch_type)` not seen before for this `(game_id,
      pitcher_id)` is inserted.
    * An existing row's level only escalates (`watch` -> `alert`); it never
      downgrades. `raised_at_pitches` only moves on an escalation (or the
      initial insert) — a same-level refresh leaves it alone.
    * `today_value`/`delta`/`sample_basis`/`pitcher_name`/`team_name`/
      `updated_at` refresh on every call regardless of level change.
    * Every row for this `(game_id, pitcher_id)` not present in `signals`
      this time is marked `active = False` (kept, never deleted) — it
      still happened.

    Returns every row this call touched (inserted or updated), not the
    ones it left untouched by marking inactive.
    """
    now = datetime.now(UTC)
    existing_rows = (
        session.execute(
            select(PitchMixAlert).where(
                PitchMixAlert.game_id == game_id, PitchMixAlert.pitcher_id == pitcher_id
            )
        )
        .scalars()
        .all()
    )
    rows_by_key = {(row.metric, row.pitch_type): row for row in existing_rows}
    current_keys = {(signal.metric, signal.pitch_type) for signal in signals}

    touched: list[PitchMixAlert] = []
    for signal in signals:
        key = (signal.metric, signal.pitch_type)
        existing = rows_by_key.get(key)
        if existing is None:
            row = PitchMixAlert(
                game_id=game_id,
                pitcher_id=pitcher_id,
                pitcher_name=pitcher_name,
                team_name=team_name,
                metric=str(signal.metric),
                pitch_type=signal.pitch_type,
                pitch_name=signal.pitch_name,
                level=str(signal.level),
                baseline_value=signal.baseline_value,
                today_value=signal.today_value,
                delta=signal.delta,
                sample_basis=signal.sample_basis,
                raised_at_pitches=live_total_pitches,
                active=True,
                first_raised_at=now,
                updated_at=now,
            )
            session.add(row)
            touched.append(row)
            continue

        escalating = existing.level == "watch" and signal.level == "alert"
        existing.pitcher_name = pitcher_name
        existing.team_name = team_name
        existing.pitch_name = signal.pitch_name
        existing.baseline_value = signal.baseline_value
        existing.today_value = signal.today_value
        existing.delta = signal.delta
        existing.sample_basis = signal.sample_basis
        existing.active = True
        existing.updated_at = now
        if escalating:
            existing.level = str(signal.level)
            existing.raised_at_pitches = live_total_pitches
        touched.append(existing)

    for key, row in rows_by_key.items():
        if key not in current_keys and row.active:
            row.active = False
            row.updated_at = now

    session.flush()
    return touched


def list_pitch_mix_alerts(
    session: Session,
    game_id: str | None = None,
    pitcher_id: int | None = None,
    active: bool | None = None,
    limit: int = 200,
) -> Sequence[PitchMixAlert]:
    """Persisted pitch-mix signals, newest updated first."""
    stmt = select(PitchMixAlert)
    if game_id is not None:
        stmt = stmt.where(PitchMixAlert.game_id == game_id)
    if pitcher_id is not None:
        stmt = stmt.where(PitchMixAlert.pitcher_id == pitcher_id)
    if active is not None:
        stmt = stmt.where(PitchMixAlert.active == active)
    stmt = stmt.order_by(PitchMixAlert.updated_at.desc(), PitchMixAlert.id.desc()).limit(limit)
    return session.execute(stmt).scalars().all()
