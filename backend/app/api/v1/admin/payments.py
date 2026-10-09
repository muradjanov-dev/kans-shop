from aiogram import Bot
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_admin, get_db
from app.api.schemas.admin import AdminAcceptPaymentIn
from app.api.schemas.order import OrderOut
from app.bot.services.order_notifications import register_order_status_notifications
from app.db.models.admin import Admin
from app.services import manual_payment_service

router = APIRouter(prefix="/admin/orders", tags=["admin-order-payments"])


@router.post("/{order_id}/payment/accept", response_model=OrderOut)
async def accept_manual_payment(
    order_id: int,
    payload: AdminAcceptPaymentIn,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
    bot: Bot = Depends(get_bot),
) -> OrderOut:
    order = await manual_payment_service.accept_card_transfer_payment(
        session,
        order_id=order_id,
        admin_id=admin.id,
        expected_receipt_version=payload.expected_receipt_version,
    )
    if manual_payment_service.consume_new_acceptance_event(session, order.id):
        register_order_status_notifications(
            session,
            bot,
            order.id,
            "orders.payment_confirmed_notification",
            action_key="admin.payment_accepted_by",
            admin_name=admin.full_name,
        )
    return OrderOut.model_validate(order)
