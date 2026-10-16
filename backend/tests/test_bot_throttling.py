from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Update

from app.bot.middlewares.throttling import ThrottlingMiddleware


async def test_throttled_update_acknowledges_nested_callback(monkeypatch) -> None:
    answer = AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer)
    callback = CallbackQuery.model_construct(id="test", chat_instance="test")
    event = Update.model_construct(update_id=1, callback_query=callback)
    redis = SimpleNamespace(incr=AsyncMock(return_value=21), expire=AsyncMock())
    handler = AsyncMock()

    await ThrottlingMiddleware(redis)(
        handler,
        event,
        {"event_from_user": SimpleNamespace(id=123), "_": lambda key: "Please wait"},
    )

    handler.assert_not_awaited()
    answer.assert_awaited_once_with("Please wait", show_alert=True)


async def test_allowed_callback_update_reaches_handler_once() -> None:
    callback = SimpleNamespace(answer=AsyncMock())
    event = Update.model_construct(update_id=1, callback_query=callback)
    redis = SimpleNamespace(incr=AsyncMock(return_value=1), expire=AsyncMock())
    handler = AsyncMock(return_value="handled")
    data = {"event_from_user": SimpleNamespace(id=123)}

    result = await ThrottlingMiddleware(redis)(handler, event, data)

    assert result == "handled"
    handler.assert_awaited_once_with(event, data)
    callback.answer.assert_not_awaited()
    redis.expire.assert_awaited_once_with("throttle:123", 60)
