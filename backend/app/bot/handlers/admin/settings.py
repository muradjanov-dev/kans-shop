from collections.abc import Awaitable, Callable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import AdminSettingEditCallback
from app.bot.keyboards.inline.admin_common import cancel_only_keyboard
from app.bot.keyboards.inline.admin_settings import SETTINGS_FIELDS, settings_list_keyboard
from app.bot.states.admin_catalog import SettingEditStates
from app.bot.utils.admin_guard import MANAGEMENT_ROLES, require_admin
from app.bot.utils.messages import require_message
from app.db.models.admin import Admin
from app.db.repositories import setting_repository

router = Router(name="admin_settings")

Sender = Callable[..., Awaitable[object]]

_NUMERIC_KEYS = ("delivery_fee", "free_delivery_from", "min_order_amount")


def _parse_setting_value(key: str, raw: str) -> object:
    if key in _NUMERIC_KEYS:
        try:
            return int(raw)
        except ValueError:
            return raw
    if key == "is_shop_open":
        return raw.strip().lower() in ("true", "1", "ha", "да", "yes")
    return raw


async def render_settings(
    send: Sender, session: AsyncSession, translator: Callable[..., str]
) -> None:
    settings_map = await setting_repository.get_all(session)
    lines = [translator("admin.settings_title"), ""]
    for key in SETTINGS_FIELDS:
        label = translator(f"admin.setting_{key}")
        value = settings_map.get(key, "-")
        lines.append(translator("admin.setting_line", label=label, value=value))
    await send("\n".join(lines), reply_markup=settings_list_keyboard(translator))


@router.callback_query(AdminSettingEditCallback.filter())
async def on_setting_edit_start(
    callback: CallbackQuery,
    callback_data: AdminSettingEditCallback,
    admin: Admin | None,
    state: FSMContext,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    await state.set_state(SettingEditStates.entering_value)
    await state.update_data(key=callback_data.key)
    label = _(f"admin.setting_{callback_data.key}")
    await message.edit_text(
        f"{label}\n\n{_('admin.setting_enter_new_value')}",
        reply_markup=cancel_only_keyboard(_),
    )
    await callback.answer()


@router.message(SettingEditStates.entering_value, F.text)
async def on_setting_value_entered(
    message: Message, session: AsyncSession, state: FSMContext, _: Callable
) -> None:
    data = await state.get_data()
    key = data["key"]
    raw = (message.text or "").strip()
    value = _parse_setting_value(key, raw)
    await setting_repository.set_value(session, key, value)
    await state.clear()
    await message.answer(_("admin.setting_updated"))
    await render_settings(message.answer, session, _)
