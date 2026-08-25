"""Middleware-level behaviour of the channel gate: who gets through, who gets stopped, and
what the blocked user is shown."""

from types import SimpleNamespace

import pytest
from aiogram.enums import ChatMemberStatus
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TgUser

from app.bot.keyboards.callback_data import CheckSubscriptionCallback, LanguageCallback
from app.bot.middlewares.subscription import SubscriptionMiddleware
from app.bot.utils import subscription
from app.core.config import settings

CHANNEL_ID = -1003642407474


class Recorder:
    """Captures what the gate sent instead of talking to Telegram."""

    def __init__(self) -> None:
        self.answers: list[str] = []
        self.alerts: list[str] = []
        self.edits: list[str] = []


@pytest.fixture(autouse=True)
def _gate_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "required_channel_id", CHANNEL_ID)
    monkeypatch.setattr(settings, "admin_ids", "")
    # channel_url() would otherwise call get_chat over the network.
    monkeypatch.setattr(settings, "required_channel_url", "https://t.me/kansshop")
    yield


def _make_message(recorder: Recorder) -> Message:
    message = Message.model_construct(
        message_id=1,
        date=None,
        chat=Chat(id=555, type="private"),
        from_user=TgUser(id=555, is_bot=False, first_name="Kamola"),
        text="/catalog",
    )

    async def answer(text: str, **kwargs: object) -> object:
        recorder.answers.append(text)
        return message

    async def edit_text(text: str, **kwargs: object) -> object:
        recorder.edits.append(text)
        return message

    object.__setattr__(message, "answer", answer)
    object.__setattr__(message, "edit_text", edit_text)
    return message


def _make_callback(recorder: Recorder, data: str) -> CallbackQuery:
    message = _make_message(recorder)
    callback = CallbackQuery.model_construct(
        id="cb1",
        from_user=TgUser(id=555, is_bot=False, first_name="Kamola"),
        chat_instance="ci",
        data=data,
        message=message,
    )

    async def answer(text: str | None = None, show_alert: bool = False, **kwargs: object):
        if text:
            recorder.alerts.append(text)

    object.__setattr__(callback, "answer", answer)
    return callback


class FakeBot:
    def __init__(self, status: ChatMemberStatus) -> None:
        self.status = status

    async def get_chat_member(self, *, chat_id: int, user_id: int) -> object:
        return SimpleNamespace(status=self.status)


def _data(bot: FakeBot, **overrides: object) -> dict:
    data = {
        "bot": bot,
        "event_from_user": TgUser(id=555, is_bot=False, first_name="Kamola"),
        "user": SimpleNamespace(id=1, first_name="Kamola", language="uz"),
        "admin": None,
        "is_new_user": False,
    }
    data.update(overrides)
    return data


async def _run(event, data) -> tuple[bool, object]:
    """Returns (handler_was_called, handler_result)."""
    called = False

    async def handler(_event, _data):
        nonlocal called
        called = True
        return "handled"

    result = await SubscriptionMiddleware(None)(handler, event, data)
    return called, result


async def test_subscriber_reaches_the_handler() -> None:
    recorder = Recorder()
    update = Update.model_construct(update_id=1, message=_make_message(recorder))
    called, result = await _run(update, _data(FakeBot(ChatMemberStatus.MEMBER)))

    assert called is True
    assert result == "handled"
    assert recorder.answers == []


async def test_non_subscriber_is_blocked_and_shown_the_gate() -> None:
    recorder = Recorder()
    update = Update.model_construct(update_id=1, message=_make_message(recorder))
    called, result = await _run(update, _data(FakeBot(ChatMemberStatus.LEFT)))

    assert called is False, "a non-subscriber must never reach the handler"
    assert result is None
    assert len(recorder.answers) == 1
    assert "obuna" in recorder.answers[0].lower()


async def test_active_admin_bypasses_the_gate() -> None:
    recorder = Recorder()
    update = Update.model_construct(update_id=1, message=_make_message(recorder))
    called, _result = await _run(
        update,
        _data(
            FakeBot(ChatMemberStatus.LEFT),
            admin=SimpleNamespace(is_active=True),
        ),
    )

    assert called is True, "admins must keep running the shop regardless of subscription"
    assert recorder.answers == []


async def test_bootstrap_admin_id_bypasses_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "admin_ids", "555")
    recorder = Recorder()
    update = Update.model_construct(update_id=1, message=_make_message(recorder))
    called, _result = await _run(update, _data(FakeBot(ChatMemberStatus.LEFT)))

    assert called is True


async def test_first_ever_update_passes_so_the_user_can_pick_a_language() -> None:
    recorder = Recorder()
    update = Update.model_construct(update_id=1, message=_make_message(recorder))
    called, _result = await _run(
        update, _data(FakeBot(ChatMemberStatus.LEFT), is_new_user=True)
    )

    assert called is True
    assert recorder.answers == []


async def test_language_callback_passes_the_gate() -> None:
    recorder = Recorder()
    callback = _make_callback(recorder, LanguageCallback(code="ru").pack())
    update = Update.model_construct(update_id=1, callback_query=callback)
    called, _result = await _run(update, _data(FakeBot(ChatMemberStatus.LEFT)))

    assert called is True, "language selection must work before the gate is satisfied"


async def test_recheck_callback_confirms_and_does_not_reach_the_handler() -> None:
    recorder = Recorder()
    callback = _make_callback(recorder, CheckSubscriptionCallback().pack())
    update = Update.model_construct(update_id=1, callback_query=callback)
    called, _result = await _run(update, _data(FakeBot(ChatMemberStatus.MEMBER)))

    assert called is False, "the recheck button is handled by the gate itself"
    assert recorder.edits, "the gate message should be replaced by a confirmation"
    assert recorder.answers, "the main menu should follow the confirmation"


async def test_recheck_while_still_unsubscribed_only_alerts() -> None:
    recorder = Recorder()
    callback = _make_callback(recorder, CheckSubscriptionCallback().pack())
    update = Update.model_construct(update_id=1, callback_query=callback)
    called, _result = await _run(update, _data(FakeBot(ChatMemberStatus.LEFT)))

    assert called is False
    assert recorder.alerts, "the user should be told they are still not subscribed"
    assert recorder.answers == [], "no second gate message — it is already on screen"


async def test_unknown_update_type_does_not_crash_the_pipeline() -> None:
    """Telegram adds update types over time; Update.event raises on ones aiogram cannot
    resolve, and that must not take the bot down."""
    update = Update.model_construct(update_id=1)
    called, result = await _run(update, _data(FakeBot(ChatMemberStatus.LEFT)))

    assert called is True
    assert result == "handled"


async def test_disabled_gate_lets_everyone_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "required_channel_id", None)
    recorder = Recorder()
    update = Update.model_construct(update_id=1, message=_make_message(recorder))
    called, _result = await _run(update, _data(FakeBot(ChatMemberStatus.LEFT)))

    assert called is True
    assert subscription.is_gate_enabled() is False
