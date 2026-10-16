from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest

from app.bot.handlers.admin import orders_list
from app.bot.keyboards.callback_data import AdminOrderFilterCallback
from app.services.common import Page


async def test_reselecting_admin_order_filter_acknowledges_before_noop_edit(monkeypatch):
    calls = []

    async def acknowledge():
        calls.append("acknowledge")

    async def list_orders(*args, **kwargs):
        calls.append("list")
        return Page(items=[], total=0, page=1, limit=10)

    message = SimpleNamespace(
        photo=[],
        edit_text=AsyncMock(
            side_effect=TelegramBadRequest(
                method=SimpleNamespace(), message="message is not modified"
            )
        ),
    )
    callback = SimpleNamespace(message=message, answer=acknowledge)
    monkeypatch.setattr(orders_list, "require_admin", AsyncMock(return_value=True))
    monkeypatch.setattr(orders_list, "require_message", AsyncMock(return_value=message))
    monkeypatch.setattr(orders_list.admin_order_service, "list_admin_orders", list_orders)

    await orders_list.on_order_filter(
        callback,
        AdminOrderFilterCallback(status="all", page=1),
        SimpleNamespace(),
        SimpleNamespace(id=7),
        lambda key, **kwargs: key,
    )

    assert calls == ["acknowledge", "list"]
    message.edit_text.assert_awaited_once()
