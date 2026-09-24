"""Small additive SQLite migrations for local deployments."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.engine import Engine

CURRENT_SCHEMA_VERSION = 2


Migration = Callable[[Engine], None]


def run_migrations(engine: Engine) -> None:
    """Apply idempotent migrations after SQLAlchemy has created known tables."""
    if engine.dialect.name != "sqlite":  # pragma: no cover - only SQLite is supported now.
        return
    _ensure_version_table(engine)
    current = _current_version(engine)
    if current < 1:
        _migration_001_role_aware_pitchers(engine)
        _set_version(engine, 1)
    if current < 2:
        _migration_002_pitch_mix_alerts(engine)
        _set_version(engine, 2)


def _ensure_version_table(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )


def _current_version(engine: Engine) -> int:
    with engine.begin() as connection:
        row = connection.execute(
            text("SELECT MAX(version) FROM schema_migrations")
        ).scalar_one_or_none()
    return int(row or 0)


def _set_version(engine: Engine, version: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("INSERT OR IGNORE INTO schema_migrations(version) VALUES (:version)"),
            {"version": version},
        )


def _migration_001_role_aware_pitchers(engine: Engine) -> None:
    with engine.begin() as connection:
        pa_columns = _columns(connection, "plate_appearances")
        if "pitcher_player_id" not in pa_columns:
            connection.execute(
                text("ALTER TABLE plate_appearances ADD COLUMN pitcher_player_id INTEGER")
            )
        if not _has_index_for(connection, "plate_appearances", ("pitcher_player_id",)):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_plate_appearances_pitcher_player_id "
                    "ON plate_appearances (pitcher_player_id)"
                )
            )

        alert_columns = _columns(connection, "alerts")
        if "subject_role" not in alert_columns:
            connection.execute(
                text(
                    "ALTER TABLE alerts ADD COLUMN subject_role VARCHAR(16) "
                    "NOT NULL DEFAULT 'batter'"
                )
            )
        connection.execute(
            text("UPDATE alerts SET subject_role = 'batter' WHERE subject_role IS NULL")
        )
        if not _has_index_for(
            connection, "alerts", ("plate_appearance_id", "subject_role", "rule_type"), unique=True
        ):
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX uq_alert_plate_appearance_role_rule "
                    "ON alerts (plate_appearance_id, subject_role, rule_type)"
                )
            )


def _migration_002_pitch_mix_alerts(engine: Engine) -> None:
    """Create `pitch_mix_alerts`.

    `Base.metadata.create_all()` (run just before this) already creates any
    table newly added to the ORM's metadata, on both a fresh database and
    an existing one — so this migration is belt-and-suspenders rather than
    load-bearing. It exists for the same reason migration 001 does: an
    explicit, ordered record of every additive schema change in
    `schema_migrations`, with its own test coverage independent of the ORM.
    """
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS pitch_mix_alerts (
                    id INTEGER PRIMARY KEY,
                    game_id VARCHAR(64) NOT NULL,
                    pitcher_id INTEGER NOT NULL,
                    pitcher_name VARCHAR(128) NOT NULL,
                    team_name VARCHAR(128),
                    metric VARCHAR(16) NOT NULL,
                    pitch_type VARCHAR(16) NOT NULL,
                    pitch_name VARCHAR(64),
                    level VARCHAR(16) NOT NULL,
                    baseline_value FLOAT NOT NULL,
                    today_value FLOAT NOT NULL,
                    delta FLOAT NOT NULL,
                    sample_basis INTEGER NOT NULL,
                    raised_at_pitches INTEGER NOT NULL,
                    active BOOLEAN NOT NULL DEFAULT 1,
                    first_raised_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    UNIQUE(game_id, pitcher_id, metric, pitch_type)
                )
                """
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_pitch_mix_alerts_game_id "
                "ON pitch_mix_alerts (game_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_pitch_mix_alerts_pitcher_id "
                "ON pitch_mix_alerts (pitcher_id)"
            )
        )


def _columns(connection, table_name: str) -> set[str]:
    rows = connection.execute(text(f"PRAGMA table_info({table_name})")).mappings()
    return {str(row["name"]) for row in rows}


def _has_index_for(
    connection, table_name: str, columns: tuple[str, ...], unique: bool = False
) -> bool:
    indexes = connection.execute(text(f"PRAGMA index_list({table_name})")).mappings()
    for index in indexes:
        if unique and not index["unique"]:
            continue
        index_name = index["name"]
        indexed_columns = tuple(
            row["name"]
            for row in connection.execute(text(f"PRAGMA index_info({index_name})")).mappings()
        )
        if indexed_columns == columns:
            return True
    return False
