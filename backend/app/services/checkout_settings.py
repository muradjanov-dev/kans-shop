"""Strictly parse the persisted settings that affect customer checkout."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

NUMERIC_CHECKOUT_SETTINGS = (
    "delivery_fee",
    "free_delivery_from",
    "min_order_amount",
)


@dataclass(frozen=True)
class CheckoutSettings:
    delivery_fee: Decimal | None
    free_delivery_from: Decimal | None
    min_order_amount: Decimal | None
    is_shop_open: bool | None
    card_number: str | None
    card_holder: str | None
    field_states: dict[str, str]


def _decimal_value(values: dict[str, Any], key: str, states: dict[str, str]) -> Decimal | None:
    if key not in values:
        states[key] = "missing"
        return None

    value = values[key]
    if value is None:
        states[key] = "null"
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        states[key] = "malformed"
        return None

    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        states[key] = "malformed"
        return None
    if not parsed.is_finite():
        states[key] = "malformed"
        return None
    states[key] = "negative" if parsed < 0 else "valid"
    return parsed


def _boolean_value(values: dict[str, Any], key: str, states: dict[str, str]) -> bool | None:
    if key not in values:
        states[key] = "missing"
        return None
    value = values[key]
    if value is None:
        states[key] = "null"
        return None
    if not isinstance(value, bool):
        states[key] = "malformed"
        return None
    states[key] = "valid"
    return value


def _optional_string(values: dict[str, Any], key: str, states: dict[str, str]) -> str | None:
    if key not in values:
        states[key] = "missing"
        return None
    value = values[key]
    if value is None:
        states[key] = "null"
        return None
    if not isinstance(value, str):
        states[key] = "malformed"
        return None
    normalized = value.strip()
    if not normalized:
        states[key] = "malformed"
        return None
    states[key] = "valid"
    return normalized


async def load_checkout_settings(session: AsyncSession) -> CheckoutSettings:
    """Load persisted purchase settings without defaults or seed data.

    `field_states` preserves whether a value was missing, explicitly null, malformed,
    negative, or valid so callers can explain why an order type is unavailable. Decimal
    zero remains valid and distinct from missing configuration.
    """
    # The typed store-settings service is the single parser used by both admin readiness and
    # phase 1 checkout. The local import keeps that module free to reuse this parser/dataclass.
    from app.services.store_settings_service import checkout_settings_from_store

    return await checkout_settings_from_store(session)


def checkout_settings_from_values(values: dict[str, Any]) -> CheckoutSettings:
    """Parse the checkout-relevant part of the persisted, typed settings map."""
    states: dict[str, str] = {}
    numeric_values = {
        key: _decimal_value(values, key, states) for key in NUMERIC_CHECKOUT_SETTINGS
    }
    return CheckoutSettings(
        delivery_fee=numeric_values["delivery_fee"],
        free_delivery_from=numeric_values["free_delivery_from"],
        min_order_amount=numeric_values["min_order_amount"],
        is_shop_open=_boolean_value(values, "is_shop_open", states),
        card_number=_optional_string(values, "card_number", states),
        card_holder=_optional_string(values, "card_holder", states),
        field_states=states,
    )
