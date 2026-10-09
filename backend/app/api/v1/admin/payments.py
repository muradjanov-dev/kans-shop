from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db
from app.api.schemas.admin import AdminAcceptPaymentIn
from app.api.schemas.order import OrderOut
from app.db.models.admin import Admin
from app.services import manual_payment_service

router = APIRouter(prefix="/admin/orders", tags=["admin-order-payments"])


@router.post("/{order_id}/payment/accept", response_model=OrderOut)
async def accept_manual_payment(
    order_id: int,
    payload: AdminAcceptPaymentIn,
    response: Response,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> OrderOut:
    order = await manual_payment_service.accept_card_transfer_payment(
        session,
        order_id=order_id,
        admin_id=admin.id,
        expected_receipt_version=payload.expected_receipt_version,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return OrderOut.model_validate(order)
