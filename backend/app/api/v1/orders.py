from uuid import UUID

from aiogram import Bot
from fastapi import APIRouter, Depends, Header, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_db
from app.api.schemas.checkout import CheckoutQuoteIn, CheckoutQuoteOut
from app.api.schemas.common import PageOut
from app.api.schemas.customer_orders import OrderHistoryItemOut, OrderTimelineEventOut
from app.api.schemas.order import (
    CheckoutIn,
    LotLinkOut,
    LotLinksOut,
    OrderOut,
    PayIn,
    PayOut,
)
from app.bot.services.order_notifications import register_new_order_notification
from app.core.config import settings
from app.core.exceptions import (
    CheckoutValidationError,
    ClientUpdateRequiredError,
    ForbiddenError,
    InvalidFileError,
)
from app.core.uploads import MAX_RECEIPT_SIZE_BYTES
from app.db.models.enums import PaymentMethod
from app.db.models.user import User
from app.db.repositories import order_repository
from app.services import (
    customer_order_service,
    order_service,
    payment_service,
    purchase_service,
)
from app.services.checkout_quote import quote_checkout
from app.services.receipt_service import attach_card_transfer_receipt
from app.services.receipt_storage import PrivateReceiptStorage

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/quote", response_model=CheckoutQuoteOut)
async def quote_order(
    payload: CheckoutQuoteIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> CheckoutQuoteOut:
    quote = await quote_checkout(
        session,
        user_id=user.id,
        order_type=payload.order_type,
        payment_method=payload.payment_method,
    )
    return CheckoutQuoteOut(
        subtotal=quote.subtotal,
        delivery_fee=quote.delivery_fee,
        total=quote.total,
        payment_methods=quote.payment_methods,
        ready=quote.ready,
        reasons=quote.reasons,
        quote_fingerprint=quote.quote_fingerprint,
    )


@router.post("", response_model=OrderOut, status_code=201)
async def checkout(
    payload: CheckoutIn,
    response: Response,
    checkout_key: UUID | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
    bot: Bot = Depends(get_bot),
) -> OrderOut:
    if payload.payment_method == PaymentMethod.CARD_TRANSFER and (
        payload.purchase_contract_version is None
    ):
        raise ClientUpdateRequiredError(
            "Reload the checkout to review the current card payment instructions."
        )

    if payload.purchase_contract_version == 1 and checkout_key is None:
        raise CheckoutValidationError(
            "Idempotency-Key is required for a quote-bound checkout."
        )

    result = await purchase_service.submit_checkout(
        session,
        user_id=user.id,
        command=purchase_service.CheckoutCommand(
            order_type=payload.order_type,
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            payment_method=payload.payment_method,
            address=payload.address,
            address_comment=payload.address_comment,
            latitude=payload.latitude,
            longitude=payload.longitude,
            comment=payload.comment,
        ),
        checkout_key=checkout_key,
        expected_quote=payload.expected_quote,
        expected_total=payload.expected_total,
        source="webapp",
        lang=user.language,
    )
    if result.created:
        register_new_order_notification(session, bot, result.order.id)
    response.status_code = 201 if result.created else 200
    return OrderOut.model_validate(result.order)


@router.get("", response_model=list[OrderOut])
async def list_my_orders(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> list[OrderOut]:
    orders, _total = await order_repository.list_by_user(session, user.id, page=1, limit=50)
    return [OrderOut.model_validate(o) for o in orders]


@router.get("/history", response_model=PageOut[OrderHistoryItemOut])
async def customer_order_history(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=24, ge=1, le=50),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> PageOut[OrderHistoryItemOut]:
    result = await customer_order_service.list_customer_orders(
        session, user_id=user.id, page=page, limit=limit
    )
    return PageOut[OrderHistoryItemOut].from_page(result)


@router.get("/{order_id}/timeline", response_model=list[OrderTimelineEventOut])
async def customer_order_timeline(
    order_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> list[OrderTimelineEventOut]:
    return await customer_order_service.customer_timeline(
        session, user_id=user.id, order_id=order_id
    )


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> OrderOut:
    order = await order_service.get_order(session, order_id)
    if order.user_id != user.id:
        raise ForbiddenError("Not your order")
    return OrderOut.model_validate(order)


@router.post("/{order_id}/receipt", response_model=OrderOut)
async def upload_receipt(
    order_id: int,
    file: UploadFile,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> OrderOut:
    order = await order_service.get_order(session, order_id)
    if order.user_id != user.id:
        raise ForbiddenError("Not your order")

    content_type = file.content_type or ""
    data = await file.read(MAX_RECEIPT_SIZE_BYTES + 1)
    if len(data) > MAX_RECEIPT_SIZE_BYTES:
        raise InvalidFileError("File too large", details={"max_bytes": MAX_RECEIPT_SIZE_BYTES})

    order = await attach_card_transfer_receipt(
        session,
        PrivateReceiptStorage(settings.private_media_root_path),
        order_id=order_id,
        owner_user_id=user.id,
        content=data,
        declared_content_type=content_type,
    )
    return OrderOut.model_validate(order)


@router.post("/{order_id}/pay", response_model=PayOut)
async def pay_order(
    order_id: int,
    payload: PayIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> PayOut:
    order = await order_repository.get_by_id_for_update(session, order_id)
    if order is None:
        order = await order_service.get_order(session, order_id)
    if order.user_id != user.id:
        raise ForbiddenError("Not your order")

    payment_url = payment_service.build_pay_url(order, payload.provider)
    return PayOut(payment_url=payment_url)


@router.get("/{order_id}/lot-links", response_model=LotLinksOut)
async def order_lot_links(
    order_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> LotLinksOut:
    """Tender checkout: where to pay each item of this order. Kept a separate call rather
    than a field on OrderOut because it reads today's `products.lot_url`, not the order's
    snapshot, and only tender orders ever need it."""
    order = await order_service.get_order(session, order_id)
    if order.user_id != user.id:
        raise ForbiddenError("Not your order")

    links, missing = await order_service.lot_links(session, order)
    return LotLinksOut(
        links=[LotLinkOut(product_name=link.product_name, url=link.url) for link in links],
        missing=missing,
    )
