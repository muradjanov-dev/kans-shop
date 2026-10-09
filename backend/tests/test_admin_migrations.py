"""Integration checks for the additive web-admin schema migration."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from secrets import token_hex

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from alembic import command
from app.core.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
PHASE1_HEAD = "1e6b8d02a9c4"
PHASE2_REVISION = "2f7c9e13b0d5"


@contextmanager
def _migration_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Config, Engine]]:
    configured_url = make_url(settings.database_url_sync)
    database_name = f"kansshop_test_admin_migration_{token_hex(6)}"
    test_url = configured_url.set(database=database_name)
    maintenance_url = configured_url.set(database="postgres")
    maintenance_engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    test_engine = None

    with maintenance_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))

    try:
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        config.set_main_option("path_separator", "os")
        monkeypatch.setattr(
            settings,
            "database_url_sync",
            test_url.render_as_string(hide_password=False),
        )
        test_engine = create_engine(test_url)
        yield config, test_engine
    finally:
        if test_engine is not None:
            test_engine.dispose()
        with maintenance_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        maintenance_engine.dispose()


def _version(engine: Engine) -> str:
    with engine.connect() as connection:
        return connection.scalar(text("SELECT version_num FROM alembic_version"))


def _insert_historical_order(connection, *, user_id: int) -> int:
    return connection.execute(
        text("""
            INSERT INTO orders (
                order_number, user_id, order_type, customer_name, customer_phone,
                subtotal, total, payment_method, receipt_file_id, receipt_url,
                receipt_storage_key, receipt_content_type
            ) VALUES (
                'KANS-PHASE1-000001', :user_id, 'delivery', 'Historical Buyer',
                '+998901234567', 5000, 5000, 'cash', 'telegram-receipt-1',
                'https://media.example/legacy-receipt-1',
                'receipts/2026/phase1-private-1.webp', 'image/webp'
            ) RETURNING id
            """),
        {"user_id": user_id},
    ).scalar_one()


def test_phase2_migration_from_phase1_head(monkeypatch: pytest.MonkeyPatch) -> None:
    with _migration_database(monkeypatch) as (config, engine):
        command.upgrade(config, PHASE1_HEAD)
        assert _version(engine) == PHASE1_HEAD

        command.upgrade(config, "head")
        assert _version(engine) == PHASE2_REVISION


def test_phase2_upgrade_preserves_orders_receipts_and_media_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _migration_database(monkeypatch) as (config, engine):
        command.upgrade(config, PHASE1_HEAD)
        with engine.begin() as connection:
            user_id = connection.execute(
                text(
                    "INSERT INTO users (telegram_id, first_name) "
                    "VALUES (9000000000000001, 'Historical Buyer') RETURNING id"
                )
            ).scalar_one()
            category_id = connection.execute(
                text(
                    "INSERT INTO categories (name_uz, name_ru, slug) "
                    "VALUES ('Tarixiy', 'Историческая', 'phase1-history') RETURNING id"
                )
            ).scalar_one()
            product_id = connection.execute(
                text(
                    "INSERT INTO products (category_id, name_uz, name_ru, sku, price, unit) "
                    "VALUES (:category_id, 'Qalam', 'Ручка', 'PHASE1-HISTORY', 5000, 'dona') "
                    "RETURNING id"
                ),
                {"category_id": category_id},
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO product_images "
                    "(product_id, url, telegram_file_id, is_main, sort_order) "
                    "VALUES (:product_id, '/media/products/1/history.webp', "
                    "'telegram-product-image-1', true, 0)"
                ),
                {"product_id": product_id},
            )
            historical_order_id = _insert_historical_order(connection, user_id=user_id)

        command.upgrade(config, "head")

        with engine.begin() as connection:
            preserved_order_ids = set(
                connection.execute(text("SELECT id FROM orders")).scalars()
            )
            original_order_ids = {historical_order_id}
            assert preserved_order_ids == original_order_ids

            receipt = connection.execute(
                text(
                    "SELECT receipt_file_id, receipt_url, receipt_storage_key, "
                    "receipt_content_type FROM orders WHERE id = :id"
                ),
                {"id": historical_order_id},
            ).one()
            assert receipt == (
                "telegram-receipt-1",
                "https://media.example/legacy-receipt-1",
                "receipts/2026/phase1-private-1.webp",
                "image/webp",
            )

            media = connection.execute(
                text(
                    "SELECT url, telegram_file_id FROM product_images "
                    "WHERE product_id = :product_id"
                ),
                {"product_id": product_id},
            ).one()
            assert media == ("/media/products/1/history.webp", "telegram-product-image-1")

            unique_constraints = connection.execute(
                text(
                    "SELECT conname, pg_get_constraintdef(oid) "
                    "FROM pg_constraint WHERE contype = 'u' AND conname IN ("
                    "'uq_admin_sessions_token_hash', "
                    "'uq_admin_order_messages_admin_order_idempotency_key', "
                    "'uq_notification_outbox_dedupe_key', "
                    "'uq_broadcast_recipients_broadcast_user'"
                    ")"
                )
            ).all()
            expected_unique_constraints = {
                "uq_admin_sessions_token_hash": "UNIQUE (token_hash)",
                "uq_admin_order_messages_admin_order_idempotency_key": (
                    "UNIQUE (admin_id, order_id, idempotency_key)"
                ),
                "uq_notification_outbox_dedupe_key": "UNIQUE (dedupe_key)",
                "uq_broadcast_recipients_broadcast_user": "UNIQUE (broadcast_id, user_id)",
            }
            assert expected_unique_constraints.items() <= dict(unique_constraints).items()

            foreign_key_actions = dict(
                connection.execute(
                    text(
                        "SELECT conname, confdeltype FROM pg_constraint "
                        "WHERE contype = 'f' AND conname IN ("
                        "'fk_admin_sessions_admin_id_admins', "
                        "'fk_admin_audit_events_actor_admin_id_admins'"
                        ")"
                    )
                ).all()
            )
            assert foreign_key_actions == {
                "fk_admin_sessions_admin_id_admins": "c",
                "fk_admin_audit_events_actor_admin_id_admins": "n",
            }

            admin_role_values = (
                connection.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum JOIN pg_type "
                        "ON pg_enum.enumtypid = pg_type.oid "
                        "WHERE pg_type.typname = 'admin_role' ORDER BY enumsortorder"
                    )
                )
                .scalars()
                .all()
            )
            assert admin_role_values == ["superadmin", "manager", "operator"]
            broadcast_status_values = (
                connection.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum JOIN pg_type "
                        "ON pg_enum.enumtypid = pg_type.oid "
                        "WHERE pg_type.typname = 'broadcast_status' ORDER BY enumsortorder"
                    )
                )
                .scalars()
                .all()
            )
            assert broadcast_status_values == [
                "draft",
                "sending",
                "completed",
                "failed",
                "cancelled",
            ]
            assert connection.execute(
                text("SELECT id, settings_version FROM store_state")
            ).one() == (1, 0)

        command.downgrade(config, PHASE1_HEAD)
        with engine.begin() as connection:
            downgraded_order = connection.execute(
                text(
                    "SELECT id, receipt_file_id, receipt_url, receipt_storage_key, "
                    "receipt_content_type FROM orders WHERE id = :id"
                ),
                {"id": historical_order_id},
            ).one()
            assert downgraded_order == (
                historical_order_id,
                "telegram-receipt-1",
                "https://media.example/legacy-receipt-1",
                "receipts/2026/phase1-private-1.webp",
                "image/webp",
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_name = 'store_state'"
                    )
                )
                == 0
            )


def test_phase2_has_single_head() -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("path_separator", "os")
    assert ScriptDirectory.from_config(config).get_heads() == [PHASE2_REVISION]
