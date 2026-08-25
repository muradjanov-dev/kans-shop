from pydantic import BaseModel


class PublicSettingsOut(BaseModel):
    delivery_fee: float | int | None = None
    free_delivery_from: float | int | None = None
    min_order_amount: float | int | None = None
    work_hours: str | None = None
    card_number: str | None = None
    card_holder: str | None = None
    support_username: str | None = None
    shop_phone: str | None = None
    is_shop_open: bool | None = None
    welcome_text_uz: str | None = None
    welcome_text_ru: str | None = None
    enabled_payment_providers: list[str] = []
