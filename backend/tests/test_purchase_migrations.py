from pathlib import Path
from secrets import token_hex

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
OLD_HEAD = "9c1f4a7be2d0"


def _migration_config(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("path_separator", "os")
    # alembic/env.py takes the URL from the shared settings object.
    monkeypatch.setattr(settings, "database_url_sync", database_url)
    return config


def _insert_order(connection, *, order_number: str, user_id: int) -> int:
    return connection.execute(
        text("""
            INSERT INTO orders (
                order_number, user_id, order_type, customer_name, customer_phone,
                subtotal, total, payment_method
            ) VALUES (
                :order_number, :user_id, 'delivery', 'Historical Buyer',
                '+998901234567', 5000, 5000, 'cash'
            ) RETURNING id
            """),
        {"order_number": order_number, "user_id": user_id},
    ).scalar_one()


def test_purchase_metadata_migration_round_trips_historical_orders(monkeypatch) -> None:
    configured_url = make_url(settings.database_url_sync)
    database_name = f"kansshop_test_purchase_migration_{token_hex(6)}"
    test_url = configured_url.set(database=database_name)
    maintenance_url = configured_url.set(database="postgres")
    maintenance_engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    test_engine = None
    with maintenance_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))

    try:
        config = _migration_config(test_url.render_as_string(hide_password=False), monkeypatch)
        command.upgrade(config, OLD_HEAD)
        test_engine = create_engine(test_url)
        with test_engine.begin() as connection:
            user_id = connection.execute(
                text(
                    "INSERT INTO users (telegram_id, first_name) "
                    "VALUES (:telegram_id, 'Historical Buyer') RETURNING id"
                ),
                {"telegram_id": 9_000_000_000_000_001},
            ).scalar_one()
            historical_ids = {
                _insert_order(connection, order_number="KANS-HIST-000001", user_id=user_id),
                _insert_order(connection, order_number="KANS-HIST-000002", user_id=user_id),
            }

        command.upgrade(config, "head")
        with test_engine.begin() as connection:
            upgraded_ids = set(
                connection.execute(text("SELECT id FROM orders ORDER BY id")).scalars()
            )
            assert upgraded_ids == historical_ids

            historical_metadata = connection.execute(
                text(
                    "SELECT checkout_key, checkout_fingerprint, payment_instructions, "
                    "receipt_storage_key, receipt_content_type, "
                    "payment_reviewed_by_admin_id, payment_reviewed_at, receipt_version "
                    "FROM orders WHERE id = :id"
                ),
                {"id": min(historical_ids)},
            ).one()
            assert historical_metadata[:-1] == (None,) * 7
            assert historical_metadata.receipt_version == 0

            checkout_key = "22222222-2222-4222-8222-222222222222"
            first_id, second_id = sorted(historical_ids)
            connection.execute(
                text("UPDATE orders SET checkout_key = :key WHERE id = :id"),
                {"key": checkout_key, "id": first_id},
            )
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    text("UPDATE orders SET checkout_key = :key WHERE id = :id"),
                    {"key": checkout_key, "id": second_id},
                )

            # Existing orders share the same user and retain NULL checkout keys, which are
            # permitted by the new unique constraint.
            new_order_id = _insert_order(
                connection, order_number="KANS-HIST-000003", user_id=user_id
            )
            new_version = connection.scalar(
                text("SELECT receipt_version FROM orders WHERE id = :id"),
                {"id": new_order_id},
            )
            assert new_version == 0

            mutation_key = "11111111-1111-4111-8111-111111111111"
            connection.execute(
                text(
                    "INSERT INTO cart_mutations (user_id, mutation_key, request_fingerprint) "
                    "VALUES (:user_id, :mutation_key, :fingerprint)"
                ),
                {"user_id": user_id, "mutation_key": mutation_key, "fingerprint": "a" * 64},
            )
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    text(
                        "INSERT INTO cart_mutations "
                        "(user_id, mutation_key, request_fingerprint) "
                        "VALUES (:user_id, :mutation_key, :fingerprint)"
                    ),
                    {
                        "user_id": user_id,
                        "mutation_key": mutation_key,
                        "fingerprint": "b" * 64,
                    },
                )

        test_engine.dispose()
        test_engine = None
        command.downgrade(config, OLD_HEAD)
        test_engine = create_engine(test_url)
        with test_engine.begin() as connection:
            downgraded_ids = set(
                connection.execute(text("SELECT id FROM orders ORDER BY id")).scalars()
            )
            assert downgraded_ids == historical_ids | {new_order_id}
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_name = 'orders' AND column_name = 'checkout_key'"
                    )
                )
                == 0
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_name = 'cart_mutations'"
                    )
                )
                == 0
            )
    finally:
        if test_engine is not None:
            test_engine.dispose()
        with maintenance_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        maintenance_engine.dispose()
