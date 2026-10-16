from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.db.models.enums import ProductUnit
from app.db.models.product import Product
from app.services.inventory_policy import InventoryPolicy


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    name_uz: str
    name_ru: str
    slug: str
    description_uz: str | None
    description_ru: str | None
    image_url: str | None
    sort_order: int
    edit_version: int
    is_active: bool
    products_count: int


class ProductImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str | None
    telegram_file_id: str | None
    is_main: bool
    sort_order: int


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    name_uz: str
    name_ru: str
    description_uz: str | None
    description_ru: str | None
    sku: str
    price: Decimal
    old_price: Decimal | None
    stock_qty: int | None
    stock_tracking_enabled: bool = True
    unit: ProductUnit
    min_order_qty: int
    is_active: bool
    is_featured: bool
    lot_url: str | None = None
    views_count: int
    sold_count: int
    edit_version: int
    images: list[ProductImageOut] = []


def public_product_out(product: Product, inventory_policy: InventoryPolicy) -> ProductOut:
    """Project internal inventory onto the public product contract."""
    result = ProductOut.model_validate(product)
    return result.model_copy(
        update={
            "stock_qty": (
                product.stock_qty if inventory_policy.stock_tracking_enabled else None
            ),
            "stock_tracking_enabled": inventory_policy.stock_tracking_enabled,
            "min_order_qty": inventory_policy.minimum_quantity(product),
        }
    )
