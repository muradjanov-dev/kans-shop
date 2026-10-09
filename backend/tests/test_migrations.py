"""Cheap structural checks on the Alembic history — they catch the mistakes that only show
up as a failed deploy: a branched history, or a model column no migration ever creates.

They do not replace running `alembic upgrade head` against Postgres; they make the common
hand-written-migration slips fail here instead of on the server.
"""

import re
from pathlib import Path

from app.db.models import Base

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"

# Columns the initial schema created under a different name, or that exist in the database
# but are not declared on a model (see the note in 54d226ca08b4 about the trigram indexes).
_ALL_MIGRATION_SOURCE = "\n".join(
    path.read_text(encoding="utf-8") for path in VERSIONS_DIR.glob("*.py")
)


def _revisions() -> dict[str, str | None]:
    revisions: dict[str, str | None] = {}
    for path in VERSIONS_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        revision = re.search(r"^revision: str = ['\"]([^'\"]+)['\"]", source, re.M)
        down = re.search(
            r"^down_revision: [^=]+ = (?:['\"]([^'\"]+)['\"]|None)$", source, re.M
        )
        assert revision, f"{path.name} has no revision id"
        assert down, f"{path.name} has no down_revision"
        revisions[revision.group(1)] = down.group(1)
    return revisions


def test_migration_history_is_a_single_unbranched_chain() -> None:
    revisions = _revisions()
    parents = [down for down in revisions.values() if down is not None]

    assert len(parents) == len(
        set(parents)
    ), "two migrations share a parent — history branched"

    heads = set(revisions) - set(parents)
    assert len(heads) == 1, f"expected exactly one head, found {sorted(heads)}"

    roots = [rev for rev, down in revisions.items() if down is None]
    assert len(roots) == 1, f"expected exactly one root, found {sorted(roots)}"

    # Every down_revision must name a revision that actually exists.
    unknown = {down for down in parents if down not in revisions}
    assert unknown == set(), f"down_revision points at missing revisions: {sorted(unknown)}"


def test_every_model_table_is_created_by_some_migration() -> None:
    missing = [
        name
        for name in Base.metadata.tables
        if re.search(rf"['\"]{re.escape(name)}['\"]", _ALL_MIGRATION_SOURCE) is None
    ]
    assert missing == [], f"tables with no migration: {missing}"


def test_new_columns_are_covered_by_a_migration() -> None:
    """Spot-checks the columns added in this round of work — the ones most likely to be
    declared on a model but forgotten in the hand-written migration."""
    for table, column in (
        ("products", "lot_url"),
        ("users", "traffic_source_id"),
        ("traffic_sources", "code"),
        ("traffic_sources", "clicks_count"),
        ("payment_transactions", "provider_transaction_id"),
        ("orders", "checkout_key"),
        ("orders", "checkout_fingerprint"),
        ("orders", "payment_instructions"),
        ("orders", "receipt_storage_key"),
        ("orders", "receipt_content_type"),
        ("orders", "receipt_version"),
        ("orders", "payment_reviewed_by_admin_id"),
        ("orders", "payment_reviewed_at"),
        ("admins", "auth_epoch"),
        ("products", "edit_version"),
        ("categories", "edit_version"),
        ("broadcasts", "photo_storage_key"),
        ("admin_sessions", "token_hash"),
        ("admin_sessions", "csrf_token"),
        ("admin_sessions", "admin_id"),
        ("admin_sessions", "auth_epoch"),
        ("admin_sessions", "idle_expires_at"),
        ("admin_sessions", "absolute_expires_at"),
        ("admin_sessions", "revoked_at"),
        ("admin_audit_events", "actor_admin_id"),
        ("admin_audit_events", "action"),
        ("admin_audit_events", "resource_type"),
        ("admin_audit_events", "resource_id"),
        ("admin_audit_events", "before_json"),
        ("admin_audit_events", "after_json"),
        ("notification_outbox", "recipient_user_id"),
        ("notification_outbox", "recipient_admin_id"),
        ("notification_outbox", "event_type"),
        ("notification_outbox", "aggregate_id"),
        ("notification_outbox", "payload_id"),
        ("notification_outbox", "dedupe_key"),
        ("notification_outbox", "status"),
        ("notification_outbox", "attempts"),
        ("notification_outbox", "next_available_at"),
        ("notification_outbox", "lease_token"),
        ("notification_outbox", "lease_expires_at"),
        ("notification_outbox", "sent_at"),
        ("notification_outbox", "last_error"),
        ("admin_order_messages", "order_id"),
        ("admin_order_messages", "admin_id"),
        ("admin_order_messages", "text"),
        ("admin_order_messages", "idempotency_key"),
        ("broadcast_recipients", "broadcast_id"),
        ("broadcast_recipients", "user_id"),
        ("broadcast_recipients", "status"),
        ("broadcast_recipients", "attempts"),
        ("broadcast_recipients", "lease_token"),
        ("broadcast_recipients", "lease_expires_at"),
        ("broadcast_recipients", "next_available_at"),
        ("broadcast_recipients", "sent_at"),
        ("broadcast_recipients", "last_error"),
        ("store_state", "id"),
        ("store_state", "settings_version"),
    ):
        assert column in Base.metadata.tables[table].c, f"{table}.{column} missing from model"
        assert re.search(
            rf"['\"]{re.escape(column)}['\"]", _ALL_MIGRATION_SOURCE
        ), f"{table}.{column} has no migration"


def test_new_payment_method_enum_values_are_added_in_migrations() -> None:
    """Postgres enums do not widen themselves — a new PaymentMethod member without an
    ALTER TYPE ... ADD VALUE fails at insert time, not at deploy time."""
    from app.db.models.enums import PaymentMethod

    initial_enum = re.search(
        r"sa\.Enum\(([^)]*?)name='payment_method'", _ALL_MIGRATION_SOURCE, re.S
    )
    assert initial_enum, "payment_method enum not found in the initial migration"
    created_values = set(re.findall(r"'([a-z_]+)'", initial_enum.group(1)))
    altered_values = set(
        re.findall(
            r"ALTER TYPE payment_method ADD VALUE IF NOT EXISTS '([a-z_]+)'",
            _ALL_MIGRATION_SOURCE,
        )
    )

    covered = created_values | altered_values
    missing = {method.value for method in PaymentMethod} - covered
    assert missing == set(), f"PaymentMethod values with no migration: {sorted(missing)}"
