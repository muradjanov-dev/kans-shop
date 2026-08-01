from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.schemas.cart import AddCartItemIn, CartOut, UpdateCartItemIn
from app.db.models.cart import Cart
from app.db.models.user import User
from app.services import cart_service

router = APIRouter(prefix="/cart", tags=["cart"])


def _cart_to_out(cart: Cart) -> CartOut:
    return CartOut(
        items=list(cart.items),
        subtotal=cart_service.calculate_subtotal(cart),
        items_count=cart_service.calculate_items_count(cart),
    )


@router.get("", response_model=CartOut)
async def get_cart(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> CartOut:
    cart = await cart_service.get_cart(session, user.id)
    return _cart_to_out(cart)


@router.post("/items", response_model=CartOut, status_code=201)
async def add_cart_item(
    payload: AddCartItemIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CartOut:
    await cart_service.add_item(session, user.id, payload.product_id, payload.quantity)
    cart = await cart_service.get_cart(session, user.id)
    return _cart_to_out(cart)


@router.patch("/items/{product_id}", response_model=CartOut)
async def update_cart_item(
    product_id: int,
    payload: UpdateCartItemIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CartOut:
    await cart_service.update_item_quantity(session, user.id, product_id, payload.quantity)
    cart = await cart_service.get_cart(session, user.id)
    return _cart_to_out(cart)


@router.delete("/items/{product_id}", response_model=CartOut)
async def remove_cart_item(
    product_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CartOut:
    await cart_service.remove_item(session, user.id, product_id)
    cart = await cart_service.get_cart(session, user.id)
    return _cart_to_out(cart)


@router.delete("", response_model=CartOut)
async def clear_cart(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> CartOut:
    await cart_service.clear_cart(session, user.id)
    cart = await cart_service.get_cart(session, user.id)
    return _cart_to_out(cart)
