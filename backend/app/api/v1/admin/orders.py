from datetime import date

from aiogram import Bot
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_admin, get_db
from app.api.schemas.admin import AdminOrderStatusUpdateIn
from app.api.schemas.common import PageOut
from app.api.schemas.order import OrderOut
from app.bot.services.order_notifications import (
    ACTION_KEY_BY_STATUS,
    STATUS_LABEL_KEYS,
    notify_customer_status_change,
    sync_admin_cards,
)
from app.db.models.admin import Admin
from app.db.models.enums import OrderStatus
from app.db.repositories import order_repository
from app.services import order_service
from app.services.common import Page

router = APIRouter(prefix="/admin/orders", tags=["admin-orders"])


@router.get("", response_model=PageOut[OrderOut])
async def list_orders(
    status: OrderStatus | None = Query(default=None),
    query: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    _admin: Admin = Depends(get_current_admin),
) -> PageOut[OrderOut]:
    items, total = await order_repository.list_for_admin(
        session,
        status=status,
        query=query,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit,
    )
    return PageOut[OrderOut].from_page(Page(items=items, total=total, page=page, limit=limit))


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: int,
    session: AsyncSession = Depends(get_db),
    _admin: Admin = Depends(get_current_admin),
) -> OrderOut:
    order = await order_service.get_order(session, order_id)
    return OrderOut.model_validate(order)


@router.patch("/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: int,
    payload: AdminOrderStatusUpdateIn,
    session: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
    bot: Bot = Depends(get_bot),
) -> OrderOut:
    order = await order_service.get_order(session, order_id)

    if payload.status == OrderStatus.CONFIRMED:
        order = await order_service.confirm_order(session, order, admin_id=admin.id)
    elif payload.status == OrderStatus.CANCELLED:
        order = await order_service.cancel_order(
            session, order, admin_id=admin.id, reason=payload.comment or "-"
        )
    else:
        order = await order_service.advance_status(
            session, order, payload.status, admin_id=admin.id, comment=payload.comment
        )

    await sync_admin_cards(
        bot,
        session,
        order,
        action_key=ACTION_KEY_BY_STATUS[payload.status],
        admin_name=admin.full_name,
        reason=payload.comment,
    )
    if payload.status == OrderStatus.CANCELLED:
        await notify_customer_status_change(
            bot,
            session,
            order,
            "orders.cancelled_notification",
            reason=order.cancel_reason or "",
        )
    elif payload.status == OrderStatus.CONFIRMED:
        await notify_customer_status_change(
            bot, session, order, "orders.confirmed_notification"
        )
    else:
        await notify_customer_status_change(
            bot,
            session,
            order,
            "orders.status_changed_notification",
            status_key=STATUS_LABEL_KEYS[payload.status],
        )

    return OrderOut.model_validate(order)
