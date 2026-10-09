from collections.abc import Callable

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InaccessibleMessage,
    Message,
    ReplyKeyboardRemove,
)
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.user.catalog import send_category_level, send_product_detail
from app.bot.handlers.user.web_login import send_customer_login_code
from app.bot.keyboards.callback_data import (
    ORIGIN_CATEGORY,
    ROOT_CATEGORY_ID,
    CategoryCallback,
    LanguageCallback,
)
from app.bot.keyboards.inline.language import language_keyboard
from app.bot.keyboards.inline.main_menu import main_menu_inline_keyboard
from app.bot.states.receipt_redirect import ReceiptRedirectStates
from app.bot.utils.i18n import translate
from app.core.exceptions import (
    ForbiddenError,
    OrderAlreadyProcessedError,
    OrderNotFoundError,
)
from app.db.models.admin import Admin
from app.db.models.user import User
from app.db.repositories import traffic_source_repository, user_repository
from app.services.receipt_service import get_receipt_upload_order

router = Router(name="start")


async def _handle_receipt_redirect(
    message: Message,
    session: AsyncSession,
    *,
    user_id: int,
    translator: Callable,
    state: FSMContext,
    order_id: int,
) -> None:
    """Entry point for the `receipt_{order_id}` deep link: a card_transfer order placed from
    the web storefront (no in-app photo upload there) lands the customer here to attach the
    payment receipt, mirroring the bot's own checkout receipt step but for an order that
    already exists."""
    try:
        order = await get_receipt_upload_order(
            session, order_id=order_id, owner_user_id=user_id
        )
    except (ForbiddenError, OrderAlreadyProcessedError, OrderNotFoundError):
        return

    instructions = order.payment_instructions
    card_number = instructions.get("card_number") if isinstance(instructions, dict) else None
    card_holder = instructions.get("card_holder") if isinstance(instructions, dict) else None
    if not isinstance(card_number, str) or not card_number.strip():
        await message.answer(translator("checkout.payment_instructions_unavailable"))
        return
    if not isinstance(card_holder, str) or not card_holder.strip():
        await message.answer(translator("checkout.payment_instructions_unavailable"))
        return

    await state.set_state(ReceiptRedirectStates.uploading)
    await state.update_data(order_id=order.id)
    total = f"{order.total:,.0f}".replace(",", " ")
    await message.answer(
        translator(
            "checkout.card_details",
            card_number=card_number,
            card_holder=card_holder,
            total=total,
        )
    )


# Campaign deep links: `src_<code>` is what the admin panel generates; `ref_<code>` is
# accepted as an alias so links already handed out under the older prefix keep working.
_SOURCE_PREFIXES = ("src_", "ref_")


async def _attribute_traffic_source(
    session: AsyncSession, *, user: User, payload: str, is_new_user: bool
) -> None:
    """Counts the click and, for a first-time visitor, records which campaign brought them in.
    Attribution is first-touch and never overwritten: a returning user keeps their original
    source no matter which link they arrive through later."""
    for prefix in _SOURCE_PREFIXES:
        if payload.startswith(prefix):
            code = payload.removeprefix(prefix).lower()
            break
    else:
        return

    source = await traffic_source_repository.get_by_code(session, code)
    if source is None or not source.is_active:
        return

    await traffic_source_repository.increment_clicks(session, source.id)
    if is_new_user and user.traffic_source_id is None:
        user.traffic_source_id = source.id
        await session.flush()


async def _handle_deeplink(
    message: Message,
    session: AsyncSession,
    *,
    user_id: int,
    lang: str,
    translator: Callable,
    payload: str,
    state: FSMContext,
    user: User,
    redis: Redis,
) -> None:
    if payload == "web_login":
        await send_customer_login_code(message, user, redis, translator)
    elif payload.startswith("receipt_"):
        try:
            order_id = int(payload.removeprefix("receipt_"))
        except ValueError:
            return
        await _handle_receipt_redirect(
            message,
            session,
            user_id=user_id,
            translator=translator,
            state=state,
            order_id=order_id,
        )
    elif payload.startswith("product_"):
        try:
            product_id = int(payload.removeprefix("product_"))
        except ValueError:
            return
        back = CategoryCallback(category_id=ROOT_CATEGORY_ID).pack()
        await send_product_detail(
            message.answer,
            session,
            product_id,
            user_id=user_id,
            origin=ORIGIN_CATEGORY,
            ref_id=ROOT_CATEGORY_ID,
            page=1,
            back_callback_data=back,
            lang=lang,
            translator=translator,
        )
    elif payload.startswith("category_"):
        try:
            category_id = int(payload.removeprefix("category_"))
        except ValueError:
            return
        await send_category_level(
            message.answer, session, category_id, lang=lang, translator=translator
        )
    # ref_XXX (referral) deep links are parsed but intentionally not acted upon: no referral
    # feature/schema exists in docs/DB_SCHEMA.md for this build (see docs/ASSUMPTIONS.md).


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user: User,
    is_new_user: bool,
    lang: str,
    _: Callable,
    state: FSMContext,
    admin: Admin | None,
    redis: Redis,
) -> None:
    if command.args:
        await state.update_data(deeplink=command.args)
        # Before the is_new_user early return below — a campaign link's whole purpose is to
        # attribute the users who arrive on it for the first time.
        await _attribute_traffic_source(
            session, user=user, payload=command.args, is_new_user=is_new_user
        )

    if is_new_user:
        await message.answer(_("start.choose_language"), reply_markup=language_keyboard())
        return

    is_admin = admin is not None and admin.is_active
    # ReplyKeyboardRemove clears the legacy persistent keyboard that pre-inline-menu users
    # still have pinned; the menu itself is the inline keyboard on the next message.
    await message.answer(
        _("start.welcome", name=user.first_name), reply_markup=ReplyKeyboardRemove()
    )
    await message.answer(
        _("menu.choose_action"),
        reply_markup=main_menu_inline_keyboard(_, is_admin=is_admin),
    )
    if command.args:
        await _handle_deeplink(
            message,
            session,
            user_id=user.id,
            lang=lang,
            translator=_,
            payload=command.args,
            state=state,
            user=user,
            redis=redis,
        )


@router.callback_query(LanguageCallback.filter())
async def on_language_selected(
    callback: CallbackQuery,
    callback_data: LanguageCallback,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    admin: Admin | None,
    redis: Redis,
) -> None:
    await user_repository.set_language(session, user, callback_data.code)

    def translator(key: str, **kwargs: object) -> str:
        return translate(callback_data.code, key, **kwargs)

    is_admin = admin is not None and admin.is_active
    message = callback.message
    if message is not None and not isinstance(message, InaccessibleMessage):
        await message.edit_text(translator("start.language_set"))
        await message.answer(
            translator("start.welcome", name=user.first_name),
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(
            translator("menu.choose_action"),
            reply_markup=main_menu_inline_keyboard(translator, is_admin=is_admin),
        )
    else:
        message = None

    data = await state.get_data()
    deeplink = data.get("deeplink")
    await state.clear()
    if deeplink and message is not None:
        await _handle_deeplink(
            message,
            session,
            user_id=user.id,
            lang=callback_data.code,
            translator=translator,
            payload=deeplink,
            state=state,
            user=user,
            redis=redis,
        )
    await callback.answer()
