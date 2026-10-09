"""Read-only server pricing and readiness quote for the current customer cart."""

import hashlib
import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CheckoutUnavailableError
from app.db.models.cart import CartItem
from app.db.models.enums import OrderType, PaymentMethod, PaymentProvider
from app.db.models.product import Product
from app.db.repositories import cart_repository
from app.services import payment_service
from app.services.checkout_settings import CheckoutSettings, load_checkout_settings

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class CheckoutQuote:
    subtotal: Decimal
    delivery_fee: Decimal | None
    total: Decimal | None
    payment_methods: list[PaymentMethod]
    ready: bool
    reasons: list[str]
    quote_fingerprint: str | None


def _money_string(amount: Decimal | None) -> str | None:
    if amount is None:
        return None
    return f"{amount.quantize(_CENT, rounding=ROUND_HALF_UP):.2f}"


def _setting_reason(settings: CheckoutSettings, key: str, label: str) -> str:
    state = settings.field_states.get(key, "missing")
    detail = "negative" if state == "negative" else state
    error = CheckoutUnavailableError(f"{label} setting is {detail}.")
    return f"{error.code}: {error.message}"


def _required_numeric_settings(order_type: OrderType) -> tuple[str, ...]:
    if order_type == OrderType.DELIVERY:
        return ("delivery_fee", "free_delivery_from", "min_order_amount")
    if order_type == OrderType.PICKUP:
        return ("min_order_amount",)
    return ()


def _cart_row(item: CartItem, product: Product | None) -> dict[str, object]:
    return {
        "product_id": item.product_id,
        "quantity": item.quantity,
        "live_price": _money_string(product.price) if product is not None else None,
        "active": product.is_active if product is not None else False,
    }


def _quote_fingerprint(
    *,
    items: list[CartItem],
    order_type: OrderType,
    payment_method: PaymentMethod,
    subtotal: Decimal,
    delivery_fee: Decimal | None,
    total: Decimal | None,
    settings: CheckoutSettings,
) -> str:
    relevant_keys = {
        OrderType.DELIVERY: ("delivery_fee", "free_delivery_from", "min_order_amount"),
        OrderType.PICKUP: ("min_order_amount",),
        OrderType.PREORDER: (),
    }[order_type]
    applicable_settings: dict[str, object] = {
        "is_shop_open": settings.is_shop_open,
    }
    for key in relevant_keys:
        value = getattr(settings, key)
        applicable_settings[key] = {
            "state": settings.field_states.get(key, "missing"),
            "value": _money_string(value),
        }
    applicable_settings["is_shop_open_state"] = settings.field_states.get(
        "is_shop_open", "missing"
    )

    instructions: dict[str, object] = {}
    if payment_method == PaymentMethod.CARD_TRANSFER:
        instructions = {
            "card_number": settings.card_number,
            "card_number_state": settings.field_states.get("card_number", "missing"),
            "card_holder": settings.card_holder,
            "card_holder_state": settings.field_states.get("card_holder", "missing"),
        }
    elif payment_method == PaymentMethod.TENDER:
        instructions = {
            "lot_urls": sorted(
                (item.product.lot_url or "") if item.product is not None else ""
                for item in items
            )
        }

    canonical = {
        "cart": [
            _cart_row(item, item.product)
            for item in sorted(items, key=lambda current: current.product_id)
        ],
        "order_type": order_type.value,
        "payment_method": payment_method.value,
        "subtotal": _money_string(subtotal),
        "delivery_fee": _money_string(delivery_fee),
        "total": _money_string(total),
        "settings": applicable_settings,
        "instructions": instructions,
    }
    body = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


async def quote_checkout(
    session: AsyncSession,
    *,
    user_id: int,
    order_type: OrderType,
    payment_method: PaymentMethod,
) -> CheckoutQuote:
    settings = await load_checkout_settings(session)
    cart = await cart_repository.get_active_cart(session, user_id)
    items = list(cart.items) if cart is not None else []
    reasons: list[str] = []
    blockers: list[str] = []

    if not items:
        blockers.append("Cart is empty.")

    subtotal = Decimal("0")
    missing_product = False
    stock_ok = True
    for item in items:
        product = item.product
        if product is None:
            missing_product = True
            stock_ok = False
            blockers.append(f"CHECKOUT_UNAVAILABLE: Product {item.product_id} is unavailable.")
            continue
        subtotal += product.price * item.quantity
        if not product.is_active:
            stock_ok = False
            blockers.append(f"Product {product.name_uz} is no longer active.")
        if product.stock_qty < item.quantity:
            stock_ok = False
            blockers.append(
                f"Insufficient stock for {product.name_uz} "
                f"(available {product.stock_qty}, requested {item.quantity})."
            )

    required_numeric = _required_numeric_settings(order_type)
    labels = {
        "delivery_fee": "Delivery fee",
        "free_delivery_from": "Free-delivery threshold",
        "min_order_amount": "Minimum order amount",
    }
    numeric_settings_ready = True
    for key in required_numeric:
        if settings.field_states.get(key) != "valid":
            blockers.append(_setting_reason(settings, key, labels[key]))
            numeric_settings_ready = False

    if settings.is_shop_open is None:
        blockers.append(_setting_reason(settings, "is_shop_open", "Shop-open"))
    elif not settings.is_shop_open:
        blockers.append("The shop is currently closed for orders.")

    min_order = settings.min_order_amount if order_type != OrderType.PREORDER else None
    min_order_met = min_order is None or subtotal >= min_order
    if (
        min_order is not None
        and settings.field_states.get("min_order_amount") == "valid"
        and not min_order_met
    ):
        blockers.append(
            f"Minimum order amount is {min_order:.2f}; cart subtotal is {subtotal:.2f}."
        )

    delivery_fee: Decimal | None
    if order_type != OrderType.DELIVERY:
        delivery_fee = Decimal("0")
    elif (
        settings.field_states.get("delivery_fee") == "valid"
        and settings.field_states.get("free_delivery_from") == "valid"
        and settings.delivery_fee is not None
        and settings.free_delivery_from is not None
    ):
        delivery_fee = (
            Decimal("0") if subtotal >= settings.free_delivery_from else settings.delivery_fee
        )
    else:
        delivery_fee = None

    total = (
        subtotal + delivery_fee if delivery_fee is not None and not missing_product else None
    )

    base_ready = not blockers and numeric_settings_ready and min_order_met and stock_ok
    methods: list[PaymentMethod] = []
    lot_links: list[tuple[CartItem, Product]] = [
        (item, item.product)
        for item in items
        if item.product is not None and bool(item.product.lot_url)
    ]
    missing_lot_names = [
        item.product.name_uz
        for item in items
        if item.product is not None and not item.product.lot_url
    ]
    method_capabilities = {
        PaymentMethod.CASH: True,
        PaymentMethod.CARD_TRANSFER: bool(settings.card_number and settings.card_holder),
        PaymentMethod.CLICK: payment_service.is_provider_configured(PaymentProvider.CLICK),
        PaymentMethod.PAYME: payment_service.is_provider_configured(PaymentProvider.PAYME),
        PaymentMethod.PAYNET: False,
        PaymentMethod.TENDER: bool(lot_links),
    }

    if base_ready:
        methods.append(PaymentMethod.CASH)
        if order_type == OrderType.PREORDER:
            methods = [PaymentMethod.CASH]
        else:
            methods.extend(
                method
                for method in (
                    PaymentMethod.CARD_TRANSFER,
                    PaymentMethod.CLICK,
                    PaymentMethod.PAYME,
                    PaymentMethod.TENDER,
                )
                if method_capabilities[method]
            )

    if payment_method == PaymentMethod.TENDER and missing_lot_names:
        reasons.extend(
            f"Tender payment link missing for {name}." for name in missing_lot_names
        )

    if payment_method not in methods:
        method_reasons = {
            PaymentMethod.CARD_TRANSFER: "CHECKOUT_UNAVAILABLE: Card transfer requires both a card number and card holder.",
            PaymentMethod.CLICK: "CHECKOUT_UNAVAILABLE: Click merchant credentials are incomplete.",
            PaymentMethod.PAYME: "CHECKOUT_UNAVAILABLE: Payme merchant credentials are incomplete.",
            PaymentMethod.PAYNET: "CHECKOUT_UNAVAILABLE: Paynet is disabled until its merchant integration is verified.",
            PaymentMethod.TENDER: "CHECKOUT_UNAVAILABLE: Tender payment requires at least one lot payment link in this cart.",
        }
        if order_type == OrderType.PREORDER and payment_method != PaymentMethod.CASH:
            blockers.append(
                "Preorders use cash as the technical default and have no payment step."
            )
        elif payment_method in method_reasons and not method_capabilities[payment_method]:
            blockers.append(method_reasons[payment_method])
        elif payment_method == PaymentMethod.CASH and not blockers:
            blockers.append("CHECKOUT_UNAVAILABLE: Cash checkout is unavailable.")

    reasons = blockers + reasons
    fingerprint = None
    if total is not None and items and not missing_product:
        fingerprint = _quote_fingerprint(
            items=items,
            order_type=order_type,
            payment_method=payment_method,
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            total=total,
            settings=settings,
        )

    return CheckoutQuote(
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        total=total,
        payment_methods=methods,
        ready=base_ready and payment_method in methods,
        reasons=reasons,
        quote_fingerprint=fingerprint,
    )
