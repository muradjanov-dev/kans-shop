from collections.abc import Awaitable, Callable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.admin import StoreSettingsPatch
from app.bot.keyboards.callback_data import AdminSettingEditCallback
from app.bot.keyboards.inline.admin_common import cancel_only_keyboard
from app.bot.keyboards.inline.admin_settings import SETTINGS_FIELDS, settings_list_keyboard
from app.bot.states.admin_catalog import SettingEditStates
from app.bot.utils.admin_guard import MANAGEMENT_ROLES, require_admin
from app.bot.utils.messages import require_message
from app.core.exceptions import (
    AdminSessionRequiredError,
    ForbiddenError,
    StoreSettingsConflictError,
)
from app.db.models.admin import Admin
from app.services import store_settings_service

router = Router(name="admin_settings")

Sender = Callable[..., Awaitable[object]]

_NUMERIC_KEYS = {"delivery_fee", "free_delivery_from", "min_order_amount"}


def _parse_setting_value(key: str, raw: str) -> object:
    if raw in {"-", "—"}:
        return None
    if key in _NUMERIC_KEYS:
        return raw
    if key == "is_shop_open":
        normalized = raw.strip().casefold()
        if normalized in {"true", "1", "ha", "да", "yes"}:
            return True
        if normalized in {"false", "0", "yo'q", "yo‘q", "нет", "no"}:
            return False
        raise ValueError("is_shop_open must be true or false")
    return raw


async def render_settings(
    send: Sender,
    session: AsyncSession,
    translator: Callable[..., str],
    *,
    admin_id: int,
) -> None:
    snapshot = await store_settings_service.get_store_settings(session, admin_id=admin_id)
    lines = [translator("admin.settings_title"), ""]
    for key in SETTINGS_FIELDS:
        label = translator(f"admin.setting_{key}")
        value = getattr(snapshot, key)
        if value is None:
            value = translator("admin.setting_unconfigured")
        lines.append(translator("admin.setting_line", label=label, value=value))
    await send("\n".join(lines), reply_markup=settings_list_keyboard(translator))


@router.callback_query(AdminSettingEditCallback.filter())
async def on_setting_edit_start(
    callback: CallbackQuery,
    callback_data: AdminSettingEditCallback,
    session: AsyncSession,
    admin: Admin | None,
    state: FSMContext,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES, session=session):
        return
    if admin is None or callback_data.key not in SETTINGS_FIELDS:
        await callback.answer(_("admin.not_admin_alert"), show_alert=True)
        return
    message = await require_message(callback, _)
    if message is None:
        return
    try:
        snapshot = await store_settings_service.get_store_settings(session, admin_id=admin.id)
    except (AdminSessionRequiredError, ForbiddenError):
        await callback.answer(_("admin.not_admin_alert"), show_alert=True)
        return
    await state.set_state(SettingEditStates.entering_value)
    await state.update_data(key=callback_data.key, expected_version=snapshot.version)
    label = _(f"admin.setting_{callback_data.key}")
    await message.edit_text(
        f"{label}\n\n{_('admin.setting_enter_new_value')}\n{_('admin.setting_clear_value')}",
        reply_markup=cancel_only_keyboard(_),
    )
    await callback.answer()


@router.message(SettingEditStates.entering_value, F.text)
async def on_setting_value_entered(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    admin: Admin | None,
    _: Callable,
) -> None:
    data = await state.get_data()
    key = data.get("key")
    expected_version = data.get("expected_version")
    raw = (message.text or "").strip()
    if admin is None:
        await state.clear()
        await message.answer(_("admin.settings_permission_revoked"))
        return
    if key not in SETTINGS_FIELDS or not isinstance(expected_version, int):
        await state.clear()
        await message.answer(_("admin.setting_value_invalid"))
        return

    try:
        value = _parse_setting_value(key, raw)
        changes = StoreSettingsPatch.model_validate(
            {"expected_version": expected_version, key: value}
        )
        await store_settings_service.patch_store_settings(
            session,
            admin_id=admin.id,
            expected_version=expected_version,
            changes=changes,
        )
    except (ValidationError, ValueError):
        await message.answer(_("admin.setting_value_invalid"))
        return
    except StoreSettingsConflictError:
        await state.clear()
        await message.answer(_("admin.settings_conflict"))
        return
    except (AdminSessionRequiredError, ForbiddenError):
        await state.clear()
        await message.answer(_("admin.settings_permission_revoked"))
        return

    await state.clear()
    await message.answer(_("admin.setting_updated"))
    await render_settings(message.answer, session, _, admin_id=admin.id)
