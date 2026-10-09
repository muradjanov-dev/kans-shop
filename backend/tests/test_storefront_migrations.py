from pathlib import Path
from secrets import token_hex

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
PHASE_TWO_HEAD = "2f7c9e13b0d5"


def _migration_config(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("path_separator", "os")
    monkeypatch.setattr(settings, "database_url_sync", database_url)
    return config


def test_profile_old_user_name_backfill_and_customer_migration_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_url = make_url(settings.database_url_sync)
    database_name = f"kansshop_test_customer_migration_{token_hex(6)}"
    test_url = configured_url.set(database=database_name)
    maintenance_url = configured_url.set(database="postgres")
    maintenance_engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    test_engine = None
    with maintenance_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))

    try:
        config = _migration_config(test_url.render_as_string(hide_password=False), monkeypatch)
        command.upgrade(config, PHASE_TWO_HEAD)
        test_engine = create_engine(test_url)
        with test_engine.begin() as connection:
            ids = [
                connection.execute(
                    text(
                        "INSERT INTO users (telegram_id, first_name, last_name, username) "
                        "VALUES (:telegram_id, :first_name, :last_name, :username) RETURNING id"
                    ),
                    {
                        "telegram_id": 9_300_000_000_000_001,
                        "first_name": " \tKamola\t",
                        "last_name": "\t Aliyeva \n",
                        "username": "kamola",
                    },
                ).scalar_one(),
                connection.execute(
                    text(
                        "INSERT INTO users (telegram_id, first_name, last_name, username) "
                        "VALUES (:telegram_id, :first_name, :last_name, :username) RETURNING id"
                    ),
                    {
                        "telegram_id": 9_300_000_000_000_002,
                        "first_name": "  ",
                        "last_name": None,
                        "username": "  stationery_user  ",
                    },
                ).scalar_one(),
                connection.execute(
                    text(
                        "INSERT INTO users (telegram_id, first_name, last_name, username) "
                        "VALUES (:telegram_id, :first_name, :last_name, :username) RETURNING id"
                    ),
                    {
                        "telegram_id": 9_300_000_000_000_003,
                        "first_name": " ",
                        "last_name": "  ",
                        "username": " ",
                    },
                ).scalar_one(),
                connection.execute(
                    text(
                        "INSERT INTO users (telegram_id, first_name, last_name, username) "
                        "VALUES (:telegram_id, :first_name, :last_name, :username) RETURNING id"
                    ),
                    {
                        "telegram_id": 9_300_000_000_000_004,
                        "first_name": "X" * 120,
                        "last_name": "Y" * 20,
                        "username": None,
                    },
                ).scalar_one(),
            ]

        command.upgrade(config, "head")
        with test_engine.begin() as connection:
            columns = {column["name"] for column in inspect(connection).get_columns("users")}
            assert "display_name" in columns
            names = connection.execute(
                text("SELECT id, display_name FROM users ORDER BY id")
            ).all()
            assert names == [
                (ids[0], "Kamola Aliyeva"),
                (ids[1], "stationery_user"),
                (ids[2], "Foydalanuvchi"),
                (ids[3], f"{'X' * 120} {'Y' * 7}"),
            ]
            assert inspect(connection).has_table("addresses")

            connection.execute(
                text(
                    "INSERT INTO addresses (user_id, label, address_text, is_default) "
                    "VALUES (:user_id, 'Home', 'First address', true)"
                ),
                {"user_id": ids[0]},
            )
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    text(
                        "INSERT INTO addresses (user_id, label, address_text, is_default) "
                        "VALUES (:user_id, 'Work', 'Second default', true)"
                    ),
                    {"user_id": ids[0]},
                )

        test_engine.dispose()
        test_engine = None
        command.downgrade(config, PHASE_TWO_HEAD)
        test_engine = create_engine(test_url)
        with test_engine.begin() as connection:
            columns = {column["name"] for column in inspect(connection).get_columns("users")}
            assert "display_name" not in columns
            assert not inspect(connection).has_table("addresses")
            assert connection.scalar(text("SELECT count(*) FROM users")) == 4

        test_engine.dispose()
        test_engine = None
        command.upgrade(config, "head")
        test_engine = create_engine(test_url)
        with test_engine.begin() as connection:
            names_after_round_trip = (
                connection.execute(text("SELECT display_name FROM users ORDER BY id"))
                .scalars()
                .all()
            )
            assert names_after_round_trip == [
                "Kamola Aliyeva",
                "stationery_user",
                "Foydalanuvchi",
                f"{'X' * 120} {'Y' * 7}",
            ]
    finally:
        if test_engine is not None:
            test_engine.dispose()
        with maintenance_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        maintenance_engine.dispose()
