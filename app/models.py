"""SQLAlchemy ORM models.

The interesting constraint here is `UNIQUE(game_id, at_bat_index)` on
`plate_appearances`: it is what makes ingestion idempotent. A plate appearance is
identified by the game it happened in plus its index within that game, so
re-reading the same feed can never create a second row. The repository relies on
this index for `ON CONFLICT DO NOTHING` rather than doing a SELECT-then-INSERT.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Player(Base):
    """An MLB player identity seen in a batter or pitcher role."""

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_player_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    team: Mapped[str] = mapped_column(String(128))

    plate_appearances: Mapped[list[PlateAppearance]] = relationship(
        back_populates="batter",
        cascade="all, delete-orphan",
        foreign_keys="PlateAppearance.batter_player_id",
    )
    pitching_appearances: Mapped[list[PlateAppearance]] = relationship(
        back_populates="pitcher_player", foreign_keys="PlateAppearance.pitcher_player_id"
    )


class PlateAppearance(Base):
    """One completed trip to the plate.

    The Statcast columns (`pitch_type`, `pitch_velocity`, `exit_velocity`,
    `launch_angle`) are nullable on purpose. Missing measurements stay NULL and
    are never coerced to 0 — a 0 mph exit velocity would read as a rule-relevant
    fact rather than as an absence of data.
    """

    __tablename__ = "plate_appearances"
    __table_args__ = (
        UniqueConstraint("game_id", "at_bat_index", name="uq_plate_appearance_game_at_bat"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[str] = mapped_column(String(64), index=True)
    batter_player_id: Mapped[int] = mapped_column(
        "player_id", ForeignKey("players.id"), index=True
    )
    pitcher_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id"), index=True, nullable=True
    )
    at_bat_index: Mapped[int] = mapped_column(Integer)
    inning: Mapped[int] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(64))
    pitcher_name: Mapped[str] = mapped_column("pitcher", String(128))
    pitch_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pitch_velocity: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_velocity: Mapped[float | None] = mapped_column(Float, nullable=True)
    launch_angle: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=True)

    batter: Mapped[Player] = relationship(
        back_populates="plate_appearances", foreign_keys=[batter_player_id]
    )
    pitcher_player: Mapped[Player | None] = relationship(
        back_populates="pitching_appearances", foreign_keys=[pitcher_player_id]
    )
    alerts: Mapped[list[Alert]] = relationship(
        back_populates="plate_appearance", cascade="all, delete-orphan"
    )

    @property
    def player_id(self) -> int:
        return self.batter_player_id

    @property
    def pitcher(self) -> str:
        return self.pitcher_name

    @property
    def batter_id(self) -> str:
        return self.batter.external_player_id

    @property
    def batter_name(self) -> str:
        return self.batter.name

    @property
    def batter_team(self) -> str:
        return self.batter.team

    @property
    def pitcher_id(self) -> str | None:
        return self.pitcher_player.external_player_id if self.pitcher_player else None

    @property
    def pitcher_team(self) -> str | None:
        return self.pitcher_player.team if self.pitcher_player else None


class Alert(Base):
    """A watch rule that fired for a plate appearance."""

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint(
            "plate_appearance_id",
            "subject_role",
            "rule_type",
            name="uq_alert_plate_appearance_role_rule",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plate_appearance_id: Mapped[int] = mapped_column(
        ForeignKey("plate_appearances.id"), index=True
    )
    subject_role: Mapped[str] = mapped_column(String(16), default="batter", index=True)
    rule_type: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    plate_appearance: Mapped[PlateAppearance] = relationship(back_populates="alerts")
