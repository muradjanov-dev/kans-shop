"""Server-to-server callback endpoints for Click, Payme and Paynet.

Deliberately NOT mounted under /api/v1: these calls come from the gateway's servers, not the
Mini App, so they carry no JWT and must stay exempt from RateLimitMiddleware's per-IP limits
(which only apply to /api/v1, see app/api/rate_limit.py) and from CORS. This mirrors how the
Telegram bot webhook is mounted directly in app/main.py rather than under /api/v1.

Each provider expects its own exact response envelope (not our normal `{error:{...}}` shape),
so these handlers call into app.services.payment_service and return its dict verbatim. Any
unexpected exception is caught here (rather than falling through to the app-wide JSON:API error
handler in app/api/errors.py) so the gateway still gets a response shape it can parse.
"""

from aiogram import Bot
from fastapi import APIRouter, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.services.order_notifications import (
    notify_customer_status_change,
    sync_admin_cards,
)
from app.core.logging import get_logger
from app.db.models.enums import PaymentProvider, PaymentStatus
from app.db.models.order import Order
from app.db.repositories import order_repository, payment_repository
from app.db.session import async_session_maker
from app.services import payment_service

log = get_logger(__name__)

router = APIRouter(prefix="/payments", tags=["payment-webhooks"])


async def _notify_payment_confirmed(bot: Bot, session: AsyncSession, order: Order) -> None:
    await notify_customer_status_change(
        bot, session, order, "orders.payment_confirmed_notification"
    )
    await sync_admin_cards(bot, session, order)


@router.post("/click/prepare")
async def click_prepare(request: Request) -> dict:
    form = await request.form()
    params = dict(form)
    try:
        async with async_session_maker() as session:
            result = await payment_service.click_prepare(session, params)
            await session.commit()
        return result
    except Exception:
        log.error("click_prepare_failed", params=params, exc_info=True)
        return {
            "click_trans_id": params.get("click_trans_id"),
            "merchant_trans_id": params.get("merchant_trans_id"),
            "error": payment_service.CLICK_ERROR_REQUEST_FAILED,
            "error_note": "Internal error",
        }


@router.post("/click/complete")
async def click_complete(request: Request) -> dict:
    form = await request.form()
    params = dict(form)
    bot: Bot = request.app.state.bot
    try:
        async with async_session_maker() as session:
            order = await order_repository.get_by_number(
                session, str(params.get("merchant_trans_id"))
            )
            was_paid = order is not None and order.payment_status == PaymentStatus.PAID

            result = await payment_service.click_complete(session, params)
            await session.commit()

            if order is not None and not was_paid:
                await session.refresh(order)
                if order.payment_status == PaymentStatus.PAID:
                    await _notify_payment_confirmed(bot, session, order)
                    await session.commit()
        return result
    except Exception:
        log.error("click_complete_failed", params=params, exc_info=True)
        return {
            "click_trans_id": params.get("click_trans_id"),
            "merchant_trans_id": params.get("merchant_trans_id"),
            "error": payment_service.CLICK_ERROR_REQUEST_FAILED,
            "error_note": "Internal error",
        }


@router.post("/payme")
async def payme_rpc(
    request: Request, authorization: str | None = Header(default=None)
) -> dict:
    body = await request.json()
    bot: Bot = request.app.state.bot
    if not payment_service.verify_payme_auth(authorization):
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "error": {"code": -32504, "message": "Insufficient privileges"},
        }
    try:
        async with async_session_maker() as session:
            order = None
            if body.get("method") == "PerformTransaction":
                tx = await payment_repository.get_by_provider_tx_id(
                    session,
                    PaymentProvider.PAYME,
                    str((body.get("params") or {}).get("id")),
                )
                if tx is not None:
                    order = await order_repository.get_by_id(session, tx.order_id)
            was_paid = order is not None and order.payment_status == PaymentStatus.PAID

            result = await payment_service.payme_handle_rpc(session, body)
            await session.commit()

            if order is not None and not was_paid:
                await session.refresh(order)
                if order.payment_status == PaymentStatus.PAID:
                    await _notify_payment_confirmed(bot, session, order)
                    await session.commit()
        return result
    except Exception:
        log.error("payme_rpc_failed", body=body, exc_info=True)
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "error": {"code": -32603, "message": "Internal error"},
        }


@router.post("/paynet/check")
async def paynet_check(request: Request) -> dict:
    payload = await request.json()
    try:
        async with async_session_maker() as session:
            result = await payment_service.paynet_check(session, payload)
            await session.commit()
        return result
    except Exception:
        log.error("paynet_check_failed", payload=payload, exc_info=True)
        return {"result": 0, "error": "Internal error"}


@router.post("/paynet/pay")
async def paynet_pay(request: Request) -> dict:
    payload = await request.json()
    bot: Bot = request.app.state.bot
    try:
        async with async_session_maker() as session:
            order = await order_repository.get_by_number(session, str(payload.get("order_id")))
            was_paid = order is not None and order.payment_status == PaymentStatus.PAID

            result = await payment_service.paynet_pay(session, payload)
            await session.commit()

            if order is not None and not was_paid:
                await session.refresh(order)
                if order.payment_status == PaymentStatus.PAID:
                    await _notify_payment_confirmed(bot, session, order)
                    await session.commit()
        return result
    except Exception:
        log.error("paynet_pay_failed", payload=payload, exc_info=True)
        return {"result": 0, "error": "Internal error"}
