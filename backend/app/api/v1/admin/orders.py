from datetime import date

from aiogram import Bot
from fastapi import APIRouter, Depends, Query, Response
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_admin, get_db
from app.api.schemas.admin import (
    AdminOrderDetailOut,
    AdminOrderMessageIn,
    AdminOrderMessageQueuedOut,
    AdminOrderStatusUpdateIn,
)
from app.api.schemas.common import PageOut
from app.api.schemas.order import OrderOut
from app.bot.services.order_notifications import (
    ACTION_KEY_BY_STATUS,
    STATUS_LABEL_KEYS,
    register_order_status_notifications,
)
from app.db.models.admin import Admin
from app.db.models.enums import OrderStatus
from app.services import admin_order_service, order_service

router = APIRouter(prefix="/admin/orders", tags=["admin-orders"])


@router.get("", response_model=PageOut[OrderOut])
async def list_orders(
    response: Response,
    status: OrderStatus | None = Query(default=None),
    query: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db, scope="function"),
    _admin: Admin = Depends(get_current_admin),
) -> PageOut[OrderOut]:
    page_result = await admin_order_service.list_admin_orders(
        session,
        admin_id=_admin.id,
        status=status,
        query=query,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return PageOut[OrderOut].from_page(page_result)


@router.get("/{order_id}", response_model=AdminOrderDetailOut)
async def get_order(
    order_id: int,
    response: Response,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> AdminOrderDetailOut:
    detail = await admin_order_service.get_admin_order(
        session, admin_id=admin.id, order_id=order_id
    )
    response.headers["Cache-Control"] = "private, no-store"
    return AdminOrderDetailOut(
        **OrderOut.model_validate(detail.order).model_dump(exclude={"has_receipt"}),
        status_history=detail.status_history,
        payment_history=detail.payment_history,
        payment_review_history=detail.payment_review_history,
    )


@router.patch("/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: int,
    response: Response,
    payload: AdminOrderStatusUpdateIn,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
    bot: Bot = Depends(get_bot),
) -> OrderOut:
    live_admin = await admin_order_service.load_order_admin(
        session, admin_id=admin.id, lock=True
    )
    order = await order_service.get_order(session, order_id)

    if payload.status == OrderStatus.CONFIRMED:
        order = await order_service.confirm_order(session, order, admin_id=live_admin.id)
    elif payload.status == OrderStatus.CANCELLED:
        order = await order_service.cancel_order(
            session, order, admin_id=live_admin.id, reason=payload.comment or "-"
        )
    else:
        order = await order_service.advance_status(
            session, order, payload.status, admin_id=live_admin.id, comment=payload.comment
        )

    if payload.status == OrderStatus.CANCELLED:
        notification_key = "orders.cancelled_notification"
        reason = order.cancel_reason or ""
        status_key = None
    elif payload.status == OrderStatus.CONFIRMED:
        notification_key = "orders.confirmed_notification"
        reason = None
        status_key = None
    else:
        notification_key = "orders.status_changed_notification"
        reason = None
        status_key = STATUS_LABEL_KEYS[payload.status]

    register_order_status_notifications(
        session,
        bot,
        order.id,
        notification_key,
        status_key=status_key,
        action_key=ACTION_KEY_BY_STATUS[payload.status],
        admin_name=live_admin.full_name,
        reason=reason,
    )

    response.headers["Cache-Control"] = "private, no-store"
    return OrderOut.model_validate(order)


@router.post(
    "/{order_id}/message",
    response_model=AdminOrderMessageQueuedOut,
    status_code=http_status.HTTP_202_ACCEPTED,
)
async def queue_order_message(
    order_id: int,
    payload: AdminOrderMessageIn,
    response: Response,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> AdminOrderMessageQueuedOut:
    message = await admin_order_service.queue_order_message(
        session,
        admin_id=admin.id,
        order_id=order_id,
        text=payload.text,
        idempotency_key=payload.idempotency_key,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return AdminOrderMessageQueuedOut(message_id=message.id, state="queued")
