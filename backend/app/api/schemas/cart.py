from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.catalog import ProductOut


class AddCartItemIn(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)


class UpdateCartItemIn(BaseModel):
    quantity: int = Field(ge=0)


class CartItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: int
    price_snapshot: Decimal
    product: ProductOut


class CartOut(BaseModel):
    items: list[CartItemOut]
    subtotal: Decimal
    items_count: int
