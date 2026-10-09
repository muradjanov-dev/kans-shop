"""Typed, revisioned store settings shared by the admin API, bot, and checkout."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.admin import (
    STORE_SETTING_FIELDS,
    StoreSettingsPatch,
    StoreSettingsSnapshot,
)
from app.core.exceptions import StoreSettingsConflictError
from app.db.models.admin import Admin
from app.db.models.enums import AdminRole
from app.db.models.store_state import StoreState
from app.db.repositories import setting_repository
from app.services.admin_actor_service import load_live_admin
from app.services.admin_audit_service import write_audit_event
from app.services.checkout_settings import (
    CheckoutSettings,
    _optional_string,
    checkout_settings_from_values,
)
from app.services.notification_outbox_service import enqueue_outbox_event

MANAGEMENT_ROLES = frozenset({AdminRole.SUPERADMIN, AdminRole.MANAGER})


async def checkout_settings_from_store(session: AsyncSession) -> CheckoutSettings:
    """Load checkout's typed settings from the same persisted source as admin readiness."""
    values = await setting_repository.get_all(session)
    return checkout_settings_from_values(values)


async def _load_manager(
    session: AsyncSession,
    admin_id: int,
    *,
    lock: bool = False,
) -> Admin:
    return await load_live_admin(
        session,
        admin_id=admin_id,
        allowed_roles=MANAGEMENT_ROLES,
        lock=lock,
    )


async def _get_store_state(session: AsyncSession, *, lock: bool) -> StoreState:
    statement = (
        select(StoreState).where(StoreState.id == 1).execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update()
    state = await session.scalar(statement)
    if state is not None:
        return state

    # Migrations install the singleton in production. This idempotent fallback makes the
    # service safe against a just-created schema and never inserts demo setting values.
    await session.execute(
        insert(StoreState)
        .values(id=1, settings_version=0)
        .on_conflict_do_nothing(index_elements=[StoreState.id])
    )
    state = await session.scalar(statement)
    if state is None:
        raise RuntimeError("Store settings revision row could not be created")
    return state


def _snapshot_from_values(*, values: dict[str, object], version: int) -> StoreSettingsSnapshot:
    checkout = checkout_settings_from_values(values)
    states = dict(checkout.field_states)
    work_hours = _optional_string(values, "work_hours", states)
    support_username = _optional_string(values, "support_username", states)
    shop_phone = _optional_string(values, "shop_phone", states)
    welcome_text_uz = _optional_string(values, "welcome_text_uz", states)
    welcome_text_ru = _optional_string(values, "welcome_text_ru", states)

    readiness = {key: states.get(key) == "valid" for key in STORE_SETTING_FIELDS}

    def valid_amount(key: str) -> Decimal | None:
        value = getattr(checkout, key)
        return value if readiness[key] else None

    return StoreSettingsSnapshot(
        version=version,
        delivery_fee=valid_amount("delivery_fee"),
        free_delivery_from=valid_amount("free_delivery_from"),
        min_order_amount=valid_amount("min_order_amount"),
        work_hours=work_hours,
        card_number=checkout.card_number,
        card_holder=checkout.card_holder,
        support_username=support_username,
        shop_phone=shop_phone,
        is_shop_open=checkout.is_shop_open,
        welcome_text_uz=welcome_text_uz,
        welcome_text_ru=welcome_text_ru,
        readiness=readiness,
    )


async def get_store_settings(
    session: AsyncSession,
    *,
    admin_id: int,
) -> StoreSettingsSnapshot:
    await _load_manager(session, admin_id)
    state = await _get_store_state(session, lock=False)
    values = await setting_repository.get_all(session)
    return _snapshot_from_values(values=values, version=state.settings_version)


def _stored_value(value: object) -> object:
    # JSONB stores decimal strings so their precision is preserved across bot/API reads.
    return str(value) if isinstance(value, Decimal) else value


async def _notify_active_admins(
    session: AsyncSession,
    *,
    actor_admin_id: int,
    version: int,
) -> None:
    recipients = await session.scalars(
        select(Admin.id)
        .where(
            Admin.id != actor_admin_id,
            Admin.is_active.is_(True),
            Admin.notifications_enabled.is_(True),
        )
        .order_by(Admin.id)
    )
    for recipient_admin_id in recipients:
        await enqueue_outbox_event(
            session,
            event_type="store.settings.updated",
            aggregate_id=1,
            dedupe_key=f"store-settings:{version}:admin:{recipient_admin_id}",
            recipient_admin_id=recipient_admin_id,
        )


async def patch_store_settings(
    session: AsyncSession,
    *,
    admin_id: int,
    expected_version: int,
    changes: StoreSettingsPatch,
) -> StoreSettingsSnapshot:
    actor = await _load_manager(session, admin_id, lock=True)
    if expected_version < 0 or changes.expected_version != expected_version:
        raise StoreSettingsConflictError("Store settings changed; reload and retry")

    state = await _get_store_state(session, lock=True)
    if state.settings_version != expected_version:
        raise StoreSettingsConflictError("Store settings changed; reload and retry")

    changed_fields = changes.model_fields_set - {"expected_version"}
    if not changed_fields:
        values = await setting_repository.get_all(session)
        return _snapshot_from_values(values=values, version=state.settings_version)

    all_values = await setting_repository.get_all(session)
    before = {key: all_values.get(key) for key in changed_fields if key in all_values}
    for key in STORE_SETTING_FIELDS:
        if key not in changed_fields:
            continue
        value = getattr(changes, key)
        await setting_repository.set_value(session, key, _stored_value(value))
    state.settings_version += 1
    await session.flush()

    after = {key: _stored_value(getattr(changes, key)) for key in changed_fields}
    await write_audit_event(
        session,
        admin_id=actor.id,
        action="store_settings.update",
        entity="store_settings",
        entity_id=1,
        request_id=uuid4().hex,
        before=before,
        after=after,
    )
    await _notify_active_admins(
        session, actor_admin_id=actor.id, version=state.settings_version
    )

    values = await setting_repository.get_all(session)
    return _snapshot_from_values(values=values, version=state.settings_version)
