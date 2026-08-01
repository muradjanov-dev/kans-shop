from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.db.models.enums import ProductUnit


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
    stock_qty: int
    unit: ProductUnit
    min_order_qty: int
    is_active: bool
    is_featured: bool
    views_count: int
    sold_count: int
    images: list[ProductImageOut] = []
