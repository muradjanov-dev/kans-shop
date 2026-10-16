from datetime import UTC, datetime

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import DeleteMessage, EditMessageReplyMarkup, SendMessage
from aiogram.types import (
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)

from app.bot.utils.messages import answer_with_inline_keyboard


class TelegramKeyboardSession(BaseSession):
    """Offline Telegram contract: messages sent with reply keyboards cannot be edited."""

    def __init__(self):
        super().__init__()
        self.visible = {}
        self.next_id = 10
        self.reply_keyboard_visible = True
        self.edits = 0

    async def close(self):
        pass

    async def stream_content(self, url, **kwargs):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, SendMessage):
            self.next_id += 1
            self.visible[self.next_id] = method
            if isinstance(method.reply_markup, ReplyKeyboardRemove):
                self.reply_keyboard_visible = False
            return Message(
                message_id=self.next_id,
                date=datetime.now(UTC),
                chat=Chat(id=123, type="private"),
                text=method.text,
                reply_markup=(
                    method.reply_markup
                    if isinstance(method.reply_markup, InlineKeyboardMarkup)
                    else None
                ),
            ).as_(bot)
        if isinstance(method, EditMessageReplyMarkup):
            self.edits += 1
            original = self.visible[method.message_id]
            if isinstance(original.reply_markup, ReplyKeyboardRemove):
                raise TelegramBadRequest(
                    method=method, message="Bad Request: message can't be edited"
                )
            original.reply_markup = method.reply_markup
            return True
        if isinstance(method, DeleteMessage):
            del self.visible[method.message_id]
            return True
        raise AssertionError(type(method).__name__)


async def test_category_buttons_reach_telegram_without_editing_removed_reply_keyboard():
    session = TelegramKeyboardSession()
    bot = Bot(token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=session)
    incoming = Message(
        message_id=1, date=datetime.now(UTC), chat=Chat(id=123, type="private"), text="Katalog"
    ).as_(bot)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Qalamlar", callback_data="cat:1")],
            [InlineKeyboardButton(text="Daftarlar", callback_data="cat:2")],
        ]
    )

    await answer_with_inline_keyboard(incoming, "Kategoriyani tanlang:", reply_markup=keyboard)

    assert len(session.visible) == 1
    displayed = next(iter(session.visible.values()))
    assert displayed.reply_markup == keyboard
    assert session.reply_keyboard_visible is False
    assert session.edits == 0
    await bot.session.close()
