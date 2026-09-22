from __future__ import annotations

from sqlalchemy import create_engine, text

from app.migrations import run_migrations


def _legacy_engine():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE players (
                    id INTEGER PRIMARY KEY,
                    external_player_id VARCHAR(64) NOT NULL UNIQUE,
                    name VARCHAR(128) NOT NULL,
                    team VARCHAR(128) NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE plate_appearances (
                    id INTEGER PRIMARY KEY,
                    game_id VARCHAR(64) NOT NULL,
                    player_id INTEGER NOT NULL,
                    at_bat_index INTEGER NOT NULL,
                    inning INTEGER NOT NULL,
                    result VARCHAR(64) NOT NULL,
                    pitcher VARCHAR(128) NOT NULL,
                    pitch_type VARCHAR(64),
                    pitch_velocity FLOAT,
                    exit_velocity FLOAT,
                    launch_angle FLOAT,
                    is_complete BOOLEAN,
                    UNIQUE(game_id, at_bat_index),
                    FOREIGN KEY(player_id) REFERENCES players(id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE alerts (
                    id INTEGER PRIMARY KEY,
                    plate_appearance_id INTEGER NOT NULL,
                    rule_type VARCHAR(64) NOT NULL,
                    message VARCHAR(512) NOT NULL,
                    created_at DATETIME,
                    FOREIGN KEY(plate_appearance_id) REFERENCES plate_appearances(id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO players(id, external_player_id, name, team)
                VALUES (1, '657557', 'Paul DeJong', 'Chicago White Sox')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO plate_appearances(
                    id, game_id, player_id, at_bat_index, inning, result, pitcher, is_complete
                )
                VALUES (1, '776743', 1, 4, 2, 'Home Run', 'Tyler Anderson', 1)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO alerts(id, plate_appearance_id, rule_type, message, created_at)
                VALUES (1, 1, 'extra_base_hit', 'message', CURRENT_TIMESTAMP)
                """
            )
        )
    return engine


def test_migration_upgrades_phase_3_schema_and_is_idempotent():
    engine = _legacy_engine()

    run_migrations(engine)
    run_migrations(engine)

    with engine.begin() as connection:
        plate_columns = {
            row["name"]
            for row in connection.execute(text("PRAGMA table_info(plate_appearances)")).mappings()
        }
        alert_columns = {
            row["name"]
            for row in connection.execute(text("PRAGMA table_info(alerts)")).mappings()
        }
        role = connection.execute(text("SELECT subject_role FROM alerts")).scalar_one()
        pitcher_player_id = connection.execute(
            text("SELECT pitcher_player_id FROM plate_appearances")
        ).scalar_one()
        version = connection.execute(
            text("SELECT MAX(version) FROM schema_migrations")
        ).scalar_one()

    assert "pitcher_player_id" in plate_columns
    assert "subject_role" in alert_columns
    assert role == "batter"
    assert pitcher_player_id is None
    assert version == 1


def test_migration_fails_on_legacy_duplicate_alerts():
    engine = _legacy_engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO alerts(id, plate_appearance_id, rule_type, message, created_at)
                VALUES (2, 1, 'extra_base_hit', 'duplicate', CURRENT_TIMESTAMP)
                """
            )
        )

    try:
        run_migrations(engine)
    except Exception as exc:
        assert "UNIQUE" in str(exc).upper()
    else:  # pragma: no cover
        raise AssertionError("duplicate legacy alerts should block the unique index")
