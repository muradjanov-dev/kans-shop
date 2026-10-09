from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api.admin_security import ADMIN_COOKIE_NAME
from app.api.schemas.admin import StoreSettingsPatch
from app.core.config import settings
from app.db.models.admin import Admin
from app.db.models.admin_audit_event import AdminAuditEvent
from app.db.models.admin_session import AdminSession
from app.db.models.enums import AdminRole
from app.db.models.notification_outbox import NotificationOutbox
from app.db.models.setting import Setting
from app.db.models.store_state import StoreState
from app.db.repositories import setting_repository
from app.db.seed import seed_settings
from tests.api_helpers import ApiCase, make_api_case

SETTING_FIELDS = {
    "delivery_fee",
    "free_delivery_from",
    "min_order_amount",
    "work_hours",
    "card_number",
    "card_holder",
    "support_username",
    "shop_phone",
    "is_shop_open",
    "welcome_text_uz",
    "welcome_text_ru",
}


@pytest.mark.asyncio
async def test_seed_leaves_owner_entered_store_settings_unconfigured(
    db_session: AsyncSession,
) -> None:
    await db_session.execute(delete(Setting))

    await seed_settings(db_session)

    assert await setting_repository.get_all(db_session) == {}


@asynccontextmanager
async def _admin_cookie(case: ApiCase, *, role: AdminRole) -> AsyncIterator[tuple[int, str]]:
    raw_cookie = token_urlsafe(32)
    csrf_token = token_urlsafe(64)
    now = datetime.now(UTC)
    async with case.session_maker() as session:
        admin = Admin(
            telegram_id=9_300_000_000_000_000 + int(datetime.now(UTC).timestamp() * 1_000_000),
            full_name=f"Settings API {role.value}",
            role=role,
        )
        session.add(admin)
        await session.flush()
        session.add(
            AdminSession(
                admin_id=admin.id,
                token_hash=sha256(raw_cookie.encode("ascii")).hexdigest(),
                csrf_token=csrf_token,
                auth_epoch=admin.auth_epoch,
                idle_expires_at=now + timedelta(hours=12),
                absolute_expires_at=now + timedelta(days=7),
            )
        )
        await session.commit()
        admin_id = admin.id
    case.client.cookies.set(ADMIN_COOKIE_NAME, raw_cookie, path="/")
    try:
        yield admin_id, csrf_token
    finally:
        async with case.session_maker() as session:
            await session.execute(delete(Admin).where(Admin.id == admin_id))
            await session.commit()


@asynccontextmanager
async def _isolated_store_settings(case: ApiCase) -> AsyncIterator[None]:
    async with case.session_maker() as session:
        settings_before = [
            (setting.key, setting.value, setting.description)
            for setting in (await session.scalars(select(Setting))).all()
        ]
        state_before = await session.get(StoreState, 1)
        version_before = state_before.settings_version if state_before is not None else None
        admin_ids_before = set((await session.scalars(select(Admin.id))).all())
        audit_ids_before = set((await session.scalars(select(AdminAuditEvent.id))).all())
        outbox_ids_before = set((await session.scalars(select(NotificationOutbox.id))).all())
    try:
        yield
    finally:
        async with case.session_maker() as session:
            audit_delete = delete(AdminAuditEvent)
            if audit_ids_before:
                audit_delete = audit_delete.where(AdminAuditEvent.id.not_in(audit_ids_before))
            await session.execute(audit_delete)
            outbox_delete = delete(NotificationOutbox)
            if outbox_ids_before:
                outbox_delete = outbox_delete.where(
                    NotificationOutbox.id.not_in(outbox_ids_before)
                )
            await session.execute(outbox_delete)
            admin_delete = delete(Admin)
            if admin_ids_before:
                admin_delete = admin_delete.where(Admin.id.not_in(admin_ids_before))
            await session.execute(admin_delete)
            await session.execute(delete(Setting))
            session.add_all(
                [
                    Setting(key=key, value=value, description=description)
                    for key, value, description in settings_before
                ]
            )
            state = await session.get(StoreState, 1)
            if version_before is None:
                if state is not None:
                    await session.delete(state)
            elif state is None:
                session.add(StoreState(id=1, settings_version=version_before))
            else:
                state.settings_version = version_before
            await session.commit()


def _patch_headers(csrf_token: str) -> dict[str, str]:
    return {"Origin": settings.webapp_origin, "X-CSRF-Token": csrf_token}


@pytest.mark.asyncio
async def test_settings_version_conflict(test_engine: AsyncEngine) -> None:
    async with make_api_case(  # noqa: SIM117
        test_engine, base_url="https://testserver"
    ) as case:
        async with _isolated_store_settings(case):
            async with _admin_cookie(case, role=AdminRole.MANAGER) as (admin_id, csrf_token):
                async with case.session_maker() as session:
                    session.add(
                        Admin(
                            telegram_id=9_400_000_000_000_000,
                            full_name="Settings notification recipient",
                            role=AdminRole.SUPERADMIN,
                        )
                    )
                    await session.commit()

                initial = await case.client.get("/api/v1/admin/settings")
                assert initial.status_code == 200
                assert initial.json()["version"] == 0

                saved = await case.client.patch(
                    "/api/v1/admin/settings",
                    headers=_patch_headers(csrf_token),
                    json={
                        "expected_version": 0,
                        "delivery_fee": "0",
                        "work_hours": "10:00-18:00",
                        "card_number": "8600 1234 5678 9012",
                        "shop_phone": "+998901234567",
                    },
                )
                assert saved.status_code == 200
                assert saved.json()["version"] == 1
                assert saved.json()["delivery_fee"] == "0"
                assert saved.json()["work_hours"] == "10:00-18:00"
                assert saved.json()["card_number"] == "8600 1234 5678 9012"

                stale = await case.client.patch(
                    "/api/v1/admin/settings",
                    headers=_patch_headers(csrf_token),
                    json={"expected_version": 0, "min_order_amount": "5000"},
                )
                assert stale.status_code == 409
                assert stale.json()["error"]["code"] == "ENTITY_CONFLICT"

                async with case.session_maker() as session:
                    state = await session.get(StoreState, 1)
                    assert state is not None and state.settings_version == 1
                    notifications = (
                        await session.scalars(
                            select(NotificationOutbox).where(
                                NotificationOutbox.event_type == "store.settings.updated"
                            )
                        )
                    ).all()
                    assert notifications
                    assert all(item.recipient_admin_id != admin_id for item in notifications)
                    assert all(item.aggregate_id == "1" for item in notifications)
                    audit = await session.scalar(
                        select(AdminAuditEvent)
                        .where(AdminAuditEvent.resource_type == "store_settings")
                        .order_by(AdminAuditEvent.id.desc())
                    )
                    assert audit is not None
                    assert audit.after_json == {
                        "delivery_fee": "0",
                        "work_hours": "10:00-18:00",
                        "card_number": "****9012",
                    }


@pytest.mark.asyncio
async def test_settings_validation_and_null_readiness(test_engine: AsyncEngine) -> None:
    with pytest.raises(ValidationError):
        StoreSettingsPatch.model_validate({"expected_version": 0, "delivery_fee": "-0.01"})
    with pytest.raises(ValidationError):
        StoreSettingsPatch.model_validate({"expected_version": 0, "delivery_fee": 5})
    with pytest.raises(ValidationError):
        StoreSettingsPatch.model_validate({"expected_version": 0, "is_shop_open": "false"})
    with pytest.raises(ValidationError):
        StoreSettingsPatch.model_validate(
            {"expected_version": 0, "support_phone": "+998901234567"}
        )
    with pytest.raises(ValidationError):
        StoreSettingsPatch.model_validate({"expected_version": "0", "delivery_fee": "0"})
    with pytest.raises(ValidationError):
        StoreSettingsPatch.model_validate({"expected_version": 0, "shop_phone": "not-a-phone"})
    with pytest.raises(ValidationError):
        StoreSettingsPatch.model_validate(
            {"expected_version": 0, "support_username": "https://example.test"}
        )

    async with make_api_case(  # noqa: SIM117
        test_engine, base_url="https://testserver"
    ) as case:
        async with _isolated_store_settings(case):
            async with _admin_cookie(case, role=AdminRole.MANAGER) as (_admin_id, csrf_token):
                initial = await case.client.get("/api/v1/admin/settings")
                assert initial.status_code == 200
                initial_body = initial.json()
                assert initial_body["delivery_fee"] is None
                assert initial_body["free_delivery_from"] is None
                assert initial_body["min_order_amount"] is None
                assert initial_body["work_hours"] is None
                assert initial_body["is_shop_open"] is None
                assert all(value is False for value in initial_body["readiness"].values())

                invalid_negative = await case.client.patch(
                    "/api/v1/admin/settings",
                    headers=_patch_headers(csrf_token),
                    json={"expected_version": 0, "delivery_fee": "-1"},
                )
                assert invalid_negative.status_code == 422
                unknown_alias = await case.client.patch(
                    "/api/v1/admin/settings",
                    headers=_patch_headers(csrf_token),
                    json={"expected_version": 0, "support_phone": "+998901234567"},
                )
                assert unknown_alias.status_code == 422

                saved = await case.client.patch(
                    "/api/v1/admin/settings",
                    headers=_patch_headers(csrf_token),
                    json={
                        "expected_version": 0,
                        "delivery_fee": "0",
                        "free_delivery_from": "0.00",
                        "min_order_amount": "0",
                        "is_shop_open": False,
                        "work_hours": None,
                    },
                )
                assert saved.status_code == 200
                body = saved.json()
                assert body["delivery_fee"] == "0"
                assert body["free_delivery_from"] == "0.00"
                assert body["min_order_amount"] == "0"
                assert body["readiness"]["delivery_fee"] is True
                assert body["readiness"]["free_delivery_from"] is True
                assert body["readiness"]["min_order_amount"] is True
                assert body["readiness"]["is_shop_open"] is True
                assert body["is_shop_open"] is False
                assert body["work_hours"] is None
                assert body["readiness"]["work_hours"] is False

                public = await case.client.get("/api/v1/settings/public")
                assert public.status_code == 200
                assert isinstance(public.json()["delivery_fee"], (int, float))
                assert not isinstance(public.json()["delivery_fee"], str)


@pytest.mark.asyncio
async def test_settings_never_returns_gateway_secrets(test_engine: AsyncEngine) -> None:
    async with make_api_case(  # noqa: SIM117
        test_engine, base_url="https://testserver"
    ) as case:
        async with _isolated_store_settings(case):
            async with case.session_maker() as session:
                session.add_all(
                    [
                        Setting(
                            key="click_secret_key", value={"secret": "synthetic-click-secret"}
                        ),
                        Setting(key="payme_merchant_id", value="synthetic-payme-merchant"),
                        Setting(key="paynet_password", value="synthetic-paynet-password"),
                    ]
                )
                await session.commit()

            async with _admin_cookie(case, role=AdminRole.SUPERADMIN) as (
                _admin_id,
                csrf_token,
            ):
                response = await case.client.get("/api/v1/admin/settings")
                assert response.status_code == 200
                body = response.json()
                assert set(body) == SETTING_FIELDS | {"version", "readiness"}
                assert "support_phone" not in body
                encoded = response.text
                assert "synthetic-click-secret" not in encoded
                assert "synthetic-payme-merchant" not in encoded
                assert "synthetic-paynet-password" not in encoded

                rejected_provider_write = await case.client.patch(
                    "/api/v1/admin/settings",
                    headers=_patch_headers(csrf_token),
                    json={
                        "expected_version": body["version"],
                        "click_secret_key": "should-not-stick",
                    },
                )
                assert rejected_provider_write.status_code == 422


class _FakeState:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = data
        self.cleared = False

    async def get_data(self) -> dict[str, object]:
        return self.data

    async def clear(self) -> None:
        self.cleared = True
        self.data = {}


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.answers: list[str] = []

    async def answer(self, text: str, **_kwargs: object) -> None:
        self.answers.append(text)


@pytest.mark.asyncio
async def test_bot_save_rechecks_live_admin_role(
    db_session: AsyncSession, admin: Admin
) -> None:
    from app.bot.handlers.admin.settings import on_setting_value_entered

    admin.role = AdminRole.MANAGER
    await db_session.flush()
    state = _FakeState({"key": "delivery_fee", "expected_version": 0})
    message = _FakeMessage("3500")

    def translator(key: str, **kwargs: object) -> str:
        return key.format(**kwargs)

    await db_session.execute(
        update(Admin)
        .where(Admin.id == admin.id)
        .values(role=AdminRole.OPERATOR)
        .execution_options(synchronize_session=False)
    )

    await on_setting_value_entered(
        message=message, session=db_session, state=state, admin=admin, _=translator
    )

    saved_value = await setting_repository.get_value(db_session, "delivery_fee")
    assert saved_value is None
    assert state.cleared is True
    assert message.answers == ["admin.settings_permission_revoked"]
