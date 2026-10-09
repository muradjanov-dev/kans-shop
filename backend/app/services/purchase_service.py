"""Atomic, quote-bound checkout shared by the bot and HTTP adapters."""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.utils.helpers import is_valid_uz_phone, normalize_uz_phone
from app.core.exceptions import (
    CartEmptyError,
    CheckoutUnavailableError,
    CheckoutValidationError,
    ClientUpdateRequiredError,
    IdempotencyConflictError,
    MinOrderAmountError,
    OutOfStockError,
    QuoteChangedError,
)
from app.db.models.cart import Cart
from app.db.models.enums import OrderStatus, OrderType, PaymentMethod
from app.db.models.order import Order
from app.db.models.product import Product
from app.db.repositories import cart_repository, order_repository, product_repository
from app.services.checkout_quote import quote_checkout
from app.services.checkout_settings import load_checkout_settings
from app.services.purchase_locks import lock_customer_cart


@dataclass(frozen=True)
class CheckoutCommand:
    order_type: OrderType
    customer_name: str
    customer_phone: str
    payment_method: PaymentMethod = PaymentMethod.CASH
    address: str | None = None
    address_comment: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    comment: str | None = None


@dataclass(frozen=True)
class CheckoutResult:
    order: Order
    created: bool


def normalize_checkout_command(command: CheckoutCommand) -> CheckoutCommand:
    name = command.customer_name.strip()
    if not 1 <= len(name) <= 128:
        raise CheckoutValidationError("Name must contain 1 to 128 characters.")

    phone = normalize_uz_phone(command.customer_phone)
    if not is_valid_uz_phone(phone):
        raise CheckoutValidationError("Enter a valid Uzbek phone number.")

    address = command.address.strip() if command.address is not None else None
    address = address or None
    address_comment = command.address_comment.strip() if command.address_comment else None
    address_comment = address_comment or None
    comment = command.comment.strip() if command.comment else None
    comment = comment or None

    has_latitude = command.latitude is not None
    has_longitude = command.longitude is not None
    if has_latitude != has_longitude:
        raise CheckoutValidationError("Provide both delivery coordinates.")
    if has_latitude and has_longitude:
        assert command.latitude is not None and command.longitude is not None
        if not command.latitude.is_finite() or not command.longitude.is_finite():
            raise CheckoutValidationError("Delivery coordinates must be finite numbers.")
        if not Decimal("-90") <= command.latitude <= Decimal("90"):
            raise CheckoutValidationError("Latitude must be between -90 and 90.")
        if not Decimal("-180") <= command.longitude <= Decimal("180"):
            raise CheckoutValidationError("Longitude must be between -180 and 180.")

    if command.order_type == OrderType.DELIVERY:
        if address is None and not (has_latitude and has_longitude):
            raise CheckoutValidationError("A delivery address is required.")
        latitude = command.latitude
        longitude = command.longitude
    else:
        address = None
        address_comment = None
        latitude = None
        longitude = None

    return CheckoutCommand(
        order_type=command.order_type,
        customer_name=name,
        customer_phone=phone,
        payment_method=command.payment_method,
        address=address,
        address_comment=address_comment,
        latitude=latitude,
        longitude=longitude,
        comment=comment,
    )


def _money_string(amount: Decimal | None) -> str | None:
    if amount is None:
        return None
    return f"{amount:.2f}"


def _decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def checkout_request_fingerprint(
    command: CheckoutCommand, *, expected_quote: str | None, expected_total: Decimal | None
) -> str:
    """Fingerprint the normalized business payload and the quote the customer accepted."""
    canonical = {
        "order_type": command.order_type.value,
        "customer_name": command.customer_name,
        "customer_phone": command.customer_phone,
        "payment_method": command.payment_method.value,
        "address": command.address,
        "address_comment": command.address_comment,
        "latitude": _decimal_string(command.latitude),
        "longitude": _decimal_string(command.longitude),
        "comment": command.comment,
        "expected_quote": expected_quote,
        "expected_total": _money_string(expected_total),
    }
    body = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


async def _lock_and_validate_products(
    session: AsyncSession, cart: Cart
) -> list[tuple[Product, int]]:
    locked: list[tuple[Product, int]] = []
    for item in sorted(cart.items, key=lambda current: current.product_id):
        product = await product_repository.get_by_id(session, item.product_id, for_update=True)
        if product is None or not product.is_active or product.stock_qty < item.quantity:
            available = product.stock_qty if product is not None else 0
            raise OutOfStockError(
                f"Not enough stock for product {item.product_id}",
                details={"product_id": item.product_id, "available": available},
            )
        if await product_repository.get_public_by_id(session, item.product_id) is None:
            raise CheckoutUnavailableError(
                f"Product {item.product_id} is no longer available for purchase.",
                details={"product_id": item.product_id},
            )
        locked.append((product, item.quantity))
    return locked


async def submit_checkout(
    session: AsyncSession,
    *,
    user_id: int,
    command: CheckoutCommand,
    checkout_key: UUID | None,
    expected_quote: str | None,
    expected_total: Decimal | None,
    source: str,
    lang: str,
) -> CheckoutResult:
    normalized = normalize_checkout_command(command)
    if (
        source == "webapp"
        and normalized.order_type == OrderType.DELIVERY
        and normalized.address is None
    ):
        raise CheckoutValidationError("A delivery address is required for online checkout.")
    quote_bound = expected_quote is not None or expected_total is not None
    if quote_bound and (not expected_quote or expected_total is None):
        raise CheckoutValidationError("A checkout quote and total must be supplied together.")
    if (
        source == "webapp"
        and normalized.payment_method == PaymentMethod.CARD_TRANSFER
        and (expected_quote is None or checkout_key is None)
    ):
        raise ClientUpdateRequiredError(
            "Reload the checkout to review the current card payment instructions."
        )
    if quote_bound and checkout_key is None:
        raise CheckoutValidationError(
            "Idempotency-Key is required for a quote-bound checkout."
        )

    fingerprint = checkout_request_fingerprint(
        normalized, expected_quote=expected_quote, expected_total=expected_total
    )

    # Lock order is user → active cart → products. Every cart mutation uses the same order.
    cart = await lock_customer_cart(session, user_id)
    if checkout_key is not None:
        replay = await order_repository.get_by_checkout_key(session, user_id, checkout_key)
        if replay is not None:
            if replay.checkout_fingerprint != fingerprint:
                raise IdempotencyConflictError(
                    "This checkout key was already used with a different request."
                )
            return CheckoutResult(order=replay, created=False)

    if not cart.items:
        raise CartEmptyError("Cart is empty")

    locked_products = await _lock_and_validate_products(session, cart)
    quote = await quote_checkout(
        session,
        user_id=user_id,
        order_type=normalized.order_type,
        payment_method=normalized.payment_method,
    )
    if quote_bound and (
        quote.quote_fingerprint != expected_quote or quote.total != expected_total
    ):
        raise QuoteChangedError(
            "The cart or checkout settings changed. Review the latest quote before ordering."
        )
    if not quote.ready or quote.total is None:
        if normalized.order_type != OrderType.PREORDER:
            settings = await load_checkout_settings(session)
            minimum = settings.min_order_amount
            if (
                settings.field_states.get("min_order_amount") == "valid"
                and minimum is not None
                and quote.subtotal < minimum
            ):
                raise MinOrderAmountError(
                    f"Subtotal {quote.subtotal} below minimum {minimum}",
                    details={
                        "subtotal": str(quote.subtotal),
                        "min_amount": str(minimum),
                    },
                )
        raise CheckoutUnavailableError(
            "This checkout is not currently available.",
            details={"reasons": quote.reasons},
        )

    subtotal = quote.subtotal
    delivery_fee = quote.delivery_fee or Decimal("0")
    total = quote.total

    order_number = await order_repository.next_order_number(session)
    discount = Decimal("0")
    payment_instructions = None
    if normalized.payment_method == PaymentMethod.CARD_TRANSFER:
        payment_instructions = quote.payment_instructions
    order = await order_repository.create(
        session,
        order_number=order_number,
        user_id=user_id,
        order_type=normalized.order_type,
        customer_name=normalized.customer_name,
        customer_phone=normalized.customer_phone,
        address=normalized.address,
        address_comment=normalized.address_comment,
        latitude=normalized.latitude,
        longitude=normalized.longitude,
        comment=normalized.comment,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        discount=discount,
        total=total,
        payment_method=normalized.payment_method,
        source=source,
        checkout_key=str(checkout_key) if checkout_key is not None else None,
        checkout_fingerprint=fingerprint if checkout_key is not None else None,
        payment_instructions=payment_instructions,
    )

    for product, quantity in locked_products:
        name_snapshot = product.name_uz if lang == "uz" else product.name_ru
        await order_repository.add_item(
            session,
            order,
            product_id=product.id,
            product_name_snapshot=name_snapshot,
            product_sku_snapshot=product.sku,
            price=product.price,
            quantity=quantity,
        )
        await product_repository.adjust_stock(session, product, -quantity)
        await product_repository.increment_sold(session, product, quantity)

    await order_repository.add_status_history(
        session, order, from_status=None, to_status=OrderStatus.NEW
    )
    await cart_repository.clear(session, cart)

    refreshed = await order_repository.get_by_id(session, order.id)
    assert refreshed is not None
    return CheckoutResult(order=refreshed, created=True)
