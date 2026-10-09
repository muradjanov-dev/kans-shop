from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.schemas.settings import PublicSettingsOut
from app.db.models.enums import PaymentProvider
from app.db.repositories import setting_repository
from app.services import payment_service
from app.services.checkout_settings import CheckoutSettings, load_checkout_settings

router = APIRouter(prefix="/settings", tags=["settings"])


def _checkout_type_readiness(checkout: CheckoutSettings) -> dict[str, bool]:
    shop_open = checkout.is_shop_open is True

    def valid(key: str) -> bool:
        return checkout.field_states.get(key) == "valid"

    return {
        "delivery": shop_open
        and all(
            valid(key) for key in ("delivery_fee", "free_delivery_from", "min_order_amount")
        ),
        "pickup": shop_open and valid("min_order_amount"),
        "preorder": shop_open,
    }


@router.get("/public", response_model=PublicSettingsOut)
async def get_public_settings(session: AsyncSession = Depends(get_db)) -> PublicSettingsOut:
    settings_map = await setting_repository.get_all(session)
    checkout = await load_checkout_settings(session)
    enabled_providers = [
        provider.value
        for provider in PaymentProvider
        if payment_service.is_provider_configured(provider)
    ]
    public_values = {
        key: value
        for key, value in settings_map.items()
        if key in PublicSettingsOut.model_fields
    }
    for key in (
        "delivery_fee",
        "free_delivery_from",
        "min_order_amount",
        "is_shop_open",
        "card_number",
        "card_holder",
    ):
        public_values[key] = getattr(checkout, key)
    return PublicSettingsOut(
        **public_values,
        enabled_payment_providers=enabled_providers,
        checkout_type_readiness=_checkout_type_readiness(checkout),
        payment_method_readiness={
            "cash": True,
            "card_transfer": bool(checkout.card_number and checkout.card_holder),
            "click": payment_service.is_provider_configured(PaymentProvider.CLICK),
            "payme": payment_service.is_provider_configured(PaymentProvider.PAYME),
            "paynet": False,
        },
    )
